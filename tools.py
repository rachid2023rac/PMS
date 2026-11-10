import json
import os
from datetime import datetime, timedelta
import random
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ROOMS_FILE = "rooms.json"

def load_rooms():
    if not os.path.exists(ROOMS_FILE):
        return []
    with open(ROOMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_rooms(rooms):
    with open(ROOMS_FILE, "w", encoding="utf-8") as f:
        json.dump(rooms, f, indent=2, ensure_ascii=False)

def get_reservation_by_pin(pin: str) -> dict:
    """
    Recherche une réservation confirmée par le PMS via le PIN ou le reservationId.
    """
    rooms = load_rooms()
    for room in rooms:
        if (room.get("pin") == pin or room.get("reservationId") == pin) and room.get("isConfirmedByPMS", False):
            return room
    return None

def check_available_rooms() -> list:
    """Renvoie la liste des chambres disponibles et confirmées par le PMS"""
    rooms = load_rooms()
    return [r for r in rooms if r.get("status") == "available" and r.get("isConfirmedByPMS", False)]

def assign_room(pin: str, room_number: str) -> bool:
    """Assigne une chambre au client (change son statut à occupied)"""
    rooms = load_rooms()
    assigned = False
    for room in rooms:
        if room["number"] == room_number:
            room["status"] = "occupied"
            room["user_id"] = pin
            assigned = True
            break
    if assigned:
        save_rooms(rooms)
    return assigned

def update_room_from_pms(reservation_id: str, new_status: str, is_confirmed: bool, payment_status: str = None) -> bool:
    """
    Simule la synchronisation ou le webhook du PMS mettant à jour en temps réel
    le statut, la confirmation et le statut financier de la réservation.
    """
    rooms = load_rooms()
    updated = False
    for room in rooms:
        if room.get("reservationId") == reservation_id:
            room["status"] = new_status
            room["isConfirmedByPMS"] = is_confirmed
            if payment_status:
                room["paymentStatus"] = payment_status
            updated = True
            break
    if updated:
        save_rooms(rooms)
        logger.info(f"PMS Sync : Réservation {reservation_id} mise à jour (Statut: {new_status}, Confirmée: {is_confirmed})")
    return updated

def create_access_key(room_number: str, reservation_id: str) -> dict:
    """
    Simule l'appel API OHIP roomKeysExternal et retourne un objet JSON structuré
    conforme aux spécifications Oracle Hospitality Integration Platform.
    """
    now = datetime.utcnow()
    valid_from = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    valid_until = (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    mobile_key_token = f"OHIP-KEY-{room_number}-{random.randint(1000, 9999)}"

    ohip_payload_response = {
        "roomKeyResponseInfo": {
            "hotelId": "CASABLANCA",
            "reservationId": reservation_id,
            "roomNumber": room_number,
            "numberOfKeys": "1",
            "keyOptions": {
                "keyType": "MobileKey",
                "encoderId": "MOBILE_APP_ENCODER"
            },
            "validFromTimestamp": valid_from,
            "validUntilTimestamp": valid_until,
            "keyCredentials": {
                "keyTrack1": mobile_key_token,
                "status": "SUCCESS"
            }
        }
    }
    
    logger.info(f"Clé mobile OHIP générée pour la chambre {room_number} (Réservation: {reservation_id})")
    return ohip_payload_response