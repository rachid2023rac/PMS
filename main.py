import streamlit as st
import logging
import os
from langchain_core.messages import HumanMessage, AIMessage
from agents import hotel_checkin_agent, GraphState
from ocr_tool import extract_id_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting Hotel Check-in System")

st.title("Hotel Check-in System")

# --- INITIALISATION DE LA SESSION STREAMLIT ---
# --- INITIALISATION DE LA SESSION STREAMLIT --- /CLOUD
if "messages" not in st.session_state:
    st.session_state.messages = []
if "id_data" not in st.session_state:
    st.session_state.id_data = None
if "current_step" not in st.session_state:
    st.session_state.current_step = "ask_pin"
if "pin" not in st.session_state:
    st.session_state.pin = ""
if "room_number" not in st.session_state:
    st.session_state.room_number = ""
if "access_key" not in st.session_state:
    st.session_state.access_key = None

# --- SECTION OCR : Vérification d'identité dans la barre latérale ---
st.sidebar.header("🪪 Vérification d'identité")

doc_type = st.sidebar.selectbox(
    "Type de document d'identité", 
    ["Passeport", "Carte Nationale d'Identité (CIN)"]
)

files_to_process = []

if doc_type == "Passeport":
    uploaded_file = st.sidebar.file_uploader("Téléchargez le passeport", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        temp_path = "temp_passport.jpg"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.sidebar.image(temp_path, caption="Passeport téléchargé", use_container_width=True)
        files_to_process = [temp_path]
else:
    st.sidebar.info("Veuillez télécharger le Recto et le Verso de la CIN")
    recto_file = st.sidebar.file_uploader("1. CIN - Recto", type=["jpg", "jpeg", "png"], key="recto")
    verso_file = st.sidebar.file_uploader("2. CIN - Verso", type=["jpg", "jpeg", "png"], key="verso")
    
    if recto_file is not None:
        recto_path = "temp_cin_recto.jpg"
        with open(recto_path, "wb") as f:
            f.write(recto_file.getbuffer())
        st.sidebar.image(recto_path, caption="CIN Recto", use_container_width=True)
        files_to_process.append(recto_path)
        
    if verso_file is not None:
        verso_path = "temp_cin_verso.jpg"
        with open(verso_path, "wb") as f:
            f.write(verso_file.getbuffer())
        st.sidebar.image(verso_path, caption="CIN Verso", use_container_width=True)
        files_to_process.append(verso_path)

# Bouton d'analyse conditionnel
if files_to_process:
    if st.sidebar.button("Lancer l'analyse OCR"):
        with st.spinner("Extraction des données en cours..."):
            try:
                extracted_info = extract_id_data(files_to_process, doc_type)
                st.session_state.id_data = extracted_info
                st.sidebar.success("Données extraites avec succès !")
            except Exception as e:
                logger.error(f"Erreur OCR : {str(e)}")
                st.sidebar.error("Erreur lors de la lecture du document.")

# Affichage des informations structurées extraites si disponibles
if st.session_state.id_data:
    with st.sidebar.expander("📄 Informations détectées", expanded=True):
        st.write(f"**Type de document :** {st.session_state.id_data.get('document_type')}")
        st.write(f"**Nom complet :** {st.session_state.id_data.get('full_name')}")
        st.write(f"**N° de document :** {st.session_state.id_data.get('document_number')}")
        st.write(f"**Nationalité :** {st.session_state.id_data.get('nationality')}")
        st.write(f"**Date de naissance :** {st.session_state.id_data.get('birth_date')}")
        st.write(f"**Date d'expiration :** {st.session_state.id_data.get('expiry_date')}")
        
        with st.expander("Texte brut OCR"):
            st.text_area("Brut", st.session_state.id_data.get('raw_text', ''), height=100)

# --- SECTION CHAT PRINCIPALE ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("How can I assist you with your check-in?"):
    logger.info(f"Received user input: {prompt}")
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            logger.info("Initializing GraphState and invoking hotel_checkin_agent")
            
            # Transmission de l'état persistant stocké dans st.session_state à l'agent
            initial_state = {
                "messages": [HumanMessage(content=prompt)],
                "current_step": st.session_state.current_step,
                "pin": st.session_state.pin,
                "room_number": st.session_state.room_number,
                "access_key": st.session_state.access_key,
                "id_data": st.session_state.id_data
            }
            
            response = hotel_checkin_agent.invoke(initial_state)
            
            # Mise à jour de la session Streamlit avec les nouvelles valeurs de l'agent
            st.session_state.current_step = response.get("current_step", st.session_state.current_step)
            st.session_state.pin = response.get("pin", st.session_state.pin)
            st.session_state.room_number = response.get("room_number", st.session_state.room_number)
            st.session_state.access_key = response.get("access_key", st.session_state.access_key)

            logger.debug(f"Agent response: {response}")
            for message in response["messages"]:
                if isinstance(message, AIMessage):
                    logger.info(f"Assistant response: {message.content}")
                    st.markdown(message.content)
                    st.session_state.messages.append({"role": "assistant", "content": message.content})
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}", exc_info=True)
            error_message = "I apologize, but an error occurred. Please try again or contact the front desk for assistance."
            st.error(error_message)
            st.session_state.messages.append({"role": "assistant", "content": error_message})

logger.info("Hotel Check-in System session ended")