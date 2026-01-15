import streamlit as st
import asyncio
import edge_tts
import re
import tempfile
import os
import nest_asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

nest_asyncio.apply()

# --- NOVA FUNÇÃO ROBUSTA PARA RODAR EDGE TTS ---
def run_edge_tts_sync(texto, voz, arquivo_saida):
    """Roda edge_tts em thread separada para evitar conflito com Streamlit"""
    result = {"error": None, "success": False}
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            communicate = edge_tts.Communicate(texto, voz)
            loop.run_until_complete(communicate.save(arquivo_saida))
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)
        finally:
            loop.close()
    
    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join(timeout=30)
    
    if thread.is_alive():
        raise TimeoutError("Geração de áudio excedeu 30 segundos")
    
    if result["error"]:
        raise Exception(result["error"])
    
    if not result["success"]:
        raise Exception("Thread terminou sem completar a geração")
    
    # Verificar se arquivo foi criado e tem conteúdo
    if not os.path.exists(arquivo_saida) or os.path.getsize(arquivo_saida) == 0:
        raise Exception("Arquivo de áudio vazio ou não criado")

# Configuração da Página
st.set_page_config(page_title="Leitor Neural Mobile", page_icon="🎧", layout="centered")

# --- Lógica de Limpeza (Copiada e Adaptada do Desktop) ---
def limpar_texto_tts(texto):
    """Limpeza agressiva: Mantém apenas letras, números e pontuação básica"""
    if not texto: return ""
    
    # 0. Remover conteúdo entre colchetes (ex: [x], [ ], [1])
    texto = re.sub(r'\[.*?\]', '', texto)

    # 1. Substituir caracteres gráficos comuns por espaço
    texto = re.sub(r'[|•►▶●■♦▪]', ' ', texto)
    
    # 2. Remover bordas e linhas repetidas
    texto = re.sub(r'[═─_]{2,}', ' ', texto)
    
    # 3. Whitelist: Manter apenas caracteres de texto aceitáveis + URLs + %
    # \w = letras e números
    # \s = espaços
    # Pontuação: .,;:?!-()"'$%/@
    texto = re.sub(r'[^\w\s.,;:?!\-()"\u00C0-\u00FFçÇ%/@]', '', texto) 
    
    # 4. Limpar espaços duplos criados
    texto = re.sub(r'\s+', ' ', texto).strip()
    
    return texto

# --- Função Async para Gerar Áudio ---
async def gerar_audio_edge(texto, voz, arquivo_saida):
    # Remover rate="+0%" e deixar o padrão da biblioteca
    communicate = edge_tts.Communicate(texto, voz) 
    await communicate.save(arquivo_saida)

# --- Interface Gráfica Mobile-First ---
st.title("🎧 Leitor de Voz Neural")
st.caption("Versão Mobile/Web - Velocidade 1x Padrão")

# 1. Seleção de Voz
voz_opcao = st.selectbox(
    "Escolha a Voz:",
    ["Antonio (Masculina - Neural)", "Francisca (Feminina - Neural)", "Google (Português - Backup)"]
)

if "Francisca" in voz_opcao:
    voz_id = "pt-BR-FranciscaNeural"
elif "Antonio" in voz_opcao:
    voz_id = "pt-BR-AntonioNeural"
else:
    voz_id = "google"

import pypdf
from docx import Document

# 2. Entrada de Texto (Area ou Upload)
st.subheader("Entrada de Texto")
arquivo = st.file_uploader("📂 Carregar Arquivo (PDF, TXT ou Word)", type=["pdf", "txt", "docx"])

texto_inicial = ""
if arquivo is not None:
    if arquivo.name.endswith(".pdf"):
        try:
            reader = pypdf.PdfReader(arquivo)
            texto_inicial = ""
            for page in reader.pages:
                texto_inicial += page.extract_text() + "\n"
        except Exception as e:
            st.error(f"Erro ao ler PDF: {e}")
    elif arquivo.name.endswith(".docx"):
        try:
            doc = Document(arquivo)
            texto_inicial = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        except Exception as e:
            st.error(f"Erro ao ler Word: {e}")
    else: # TXT
        texto_inicial = arquivo.read().decode("utf-8")

texto_input = st.text_area("Cole seu texto ou veja o conteúdo do arquivo:", value=texto_inicial, height=200, placeholder="Cole o texto ou carregue um arquivo acima...")

# 3. Botão de Ação
if st.button("▶️ Gerar Áudio", type="primary"):
    if not texto_input.strip():
        st.warning("Por favor, cole algum texto primeiro.")
    else:
        with st.spinner("Limpando texto e criando áudio..."):
            # A. Limpeza
            texto_limpo = limpar_texto_tts(texto_input)
            
            # DEBUG: Mostrar o que será lido
            with st.expander("Ver Texto Limpo (Debug)"):
                st.write(f"**Caracteres:** {len(texto_limpo)}")
                st.write(texto_limpo)

            if not texto_limpo:
                st.error("O texto não contém caracteres válidos para leitura.")
            elif len(texto_limpo) > 5000:
                st.error(f"""
                ⚠️ **Texto muito longo!**
                
                Seu texto tem {len(texto_limpo)} caracteres.
                
                **Limite máximo:** 5000 caracteres
                
                **Solução:** Divida o texto em partes menores ou remova trechos.
                """)
            else:
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                        temp_path = fp.name
                    
                    # LOGICA DE ESCOLHA DE MOTOR
                    if voz_id == "google":
                        # MOTOR GOOGLE (gTTS)
                        from gtts import gTTS
                        tts = gTTS(text=texto_limpo, lang='pt', slow=False)
                        tts.save(temp_path)
                        st.success("Áudio Google pronto!")
                    
                    else:
                        # MOTOR NEURAL (EdgeTTS) - NOVA IMPLEMENTAÇÃO ROBUSTA
                        try:
                            run_edge_tts_sync(texto_limpo, voz_id, temp_path)
                            st.success("Áudio Neural pronto!")
                        except Exception as e_neural:
                            erro_msg = str(e_neural)
                            
                            # Mensagem amigável para erro 429 (rate limit)
                            if "429" in erro_msg or "too many" in erro_msg.lower():
                                st.warning(f"""
                                ⏱️ **Limite temporário atingido**
                                
                                A Microsoft Edge TTS tem um limite de uso gratuito. 
                                
                                **Soluções:**
                                - Aguarde 5-10 minutos e tente novamente
                                - Ou selecione a voz **"Google"** no menu acima (funciona sempre)
                                - Use textos menores para evitar o limite
                                """)
                            else:
                                st.warning(f"Voz Neural falhou ({erro_msg}). Tentando Google...")
                            
                            # Fallback para Google
                            from gtts import gTTS
                            tts = gTTS(text=texto_limpo, lang='pt', slow=False)
                            tts.save(temp_path)
                            st.success("Áudio Backup (Google) gerado!")

                    # PLAYER E DOWNLOAD (Comum a todos)
                    st.audio(temp_path, format="audio/mp3")
                    
                    with open(temp_path, "rb") as file:
                        st.download_button("💾 Baixar MP3", file, "audio_gerado.mp3", "audio/mp3")
                    
                except Exception as e:
                    st.error(f"""
                    ❌ **Erro fatal ao gerar áudio**
                    
                    **Detalhes técnicos:** {str(e)}
                    
                    **Possíveis causas:**
                    - Texto muito longo (limite: 5000 caracteres)
                    - Problema de conexão com a internet
                    - Caracteres inválidos no texto
                    
                    **Sugestões:**
                    - Tente com um texto menor
                    - Verifique o "Ver Texto Limpo" acima
                    - Aguarde alguns segundos e tente novamente
                    """)
