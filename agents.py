import logging
from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from tools import get_reservation_by_pin, assign_room, create_access_key
from pydantic import BaseModel, Field
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set")

model = ChatGroq(model="mixtral-8x7b-32768", api_key=GROQ_API_KEY)


class GraphState(BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    current_step: str = Field(default="ask_pin")
    pin: str = Field(default="")
    reservation_id: str = Field(default="")
    room_number: str = Field(default="")
    arrival_date: str = Field(default="")
    departure_date: str = Field(default="")
    payment_status: str = Field(default="")
    payment_link: str = Field(default="")
    access_key: Optional[str] = Field(default=None)
    id_data: Optional[Dict[str, Any]] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True


def run_step(state: GraphState) -> Dict[str, Any]:
    logger.info(f"Running step: {state.current_step}")
    messages = state.messages
    last_message = messages[-1].content if messages else ""

    # 1. Barrière réglementaire OCR
    if not state.id_data or not isinstance(state.id_data, dict) or not state.id_data.get("document_number"):
        logger.warning("Check-in bloqué : Pièce d'identité non validée via OCR.")
        new_message = AIMessage(
            content="S'il vous plaît, scannez vos pièces d'identité en premier avant de commencer le check-in."
        )
        return {
            "messages": messages + [new_message],
            "current_step": "ask_pin",
            "pin": state.pin,
            "reservation_id": state.reservation_id,
            "room_number": state.room_number,
            "arrival_date": state.arrival_date,
            "departure_date": state.departure_date,
            "payment_status": state.payment_status,
            "payment_link": state.payment_link,
            "access_key": state.access_key,
            "id_data": state.id_data
        }

    guest_name = f" {state.id_data['full_name']}" if state.id_data.get("full_name") else ""

    if state.current_step == "complete":
        state.current_step = "ask_pin"

    # 2. Étape : Validation du PIN / Récupération de la réservation PMS confirmée
    if state.current_step == "ask_pin":
        words = last_message.replace('"', '').replace("'", "").split()
        pin = next((w for w in words if w.isdigit() and len(w) >= 4), "")
        if not pin and len(words) > 0:
            pin = words[-1]

        # Recherche exclusive d'une réservation confirmée par le PMS
        reservation = get_reservation_by_pin(pin)
        if pin and reservation:
            logger.info(f"Réservation PMS confirmée trouvée pour le PIN {pin}")
            state.pin = pin
            state.reservation_id = reservation["reservationId"]
            state.room_number = reservation["number"]
            state.arrival_date = reservation["arrivalDate"]
            state.departure_date = reservation["departureDate"]
            state.payment_status = reservation.get("paymentStatus", "pending")
            state.payment_link = reservation.get("paymentLink", "")

            # Attribution de la chambre et génération de la clé OHIP
            ohip_response = create_access_key(state.room_number, state.reservation_id)
            state.access_key = ohip_response["roomKeyResponseInfo"]["keyCredentials"]["keyTrack1"]
            assign_room(state.pin, state.room_number)

            state.current_step = "complete"

            # Gestion conditionnelle du lien de paiement selon le statut financier
            if state.payment_status == "paid":
                payment_info = "💳 **Statut financier :** Votre séjour est **déjà réglé**. Aucun lien de paiement requis."
            else:
                payment_info = f"💳 **Statut financier :** Solde en attente. Veuillez régler via le portail sécurisé du PMS : [Accéder au paiement]({state.payment_link})"

            new_message = AIMessage(
                content=f"Merci{guest_name}. Votre réservation confirmée (Réf: **{state.reservation_id}**) a été validée par le PMS.\n\n"
                        f"🏨 **Détails du séjour :**\n"
                        f"- Chambre attribuée : **{state.room_number}**\n"
                        f"- Arrivée : {state.arrival_date}\n"
                        f"- Départ : {state.departure_date}\n\n"
                        f"🔑 **Clé d'accès mobile OHIP :** `{state.access_key}`\n\n"
                        f"{payment_info}\n\n"
                        f"Votre enregistrement est terminé. Bon séjour !"
            )
        else:
            new_message = AIMessage(
                content=f"Bienvenue{guest_name} ! Aucun dossier confirmé par le PMS ne correspond à ce code PIN. Veuillez vérifier votre référence ou contacter la réception."
            )

    else:
        state.current_step = "ask_pin"
        new_message = AIMessage(content=f"Bienvenue{guest_name} ! Veuillez me fournir votre code PIN de réservation.")

    return {
        "messages": messages + [new_message],
        "current_step": state.current_step,
        "pin": state.pin,
        "reservation_id": state.reservation_id,
        "room_number": state.room_number,
        "arrival_date": state.arrival_date,
        "departure_date": state.departure_date,
        "payment_status": state.payment_status,
        "payment_link": state.payment_link,
        "access_key": state.access_key,
        "id_data": state.id_data
    }


workflow = StateGraph(state_schema=GraphState)
workflow.add_node('agent', run_step)
workflow.set_entry_point('agent')
workflow.add_edge('agent', END)
hotel_checkin_agent = workflow.compile()