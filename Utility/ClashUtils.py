from datetime import datetime
from bson import ObjectId
from Utility import Connections


# Funzione di utilità che, dati due timeslot, controlla che questi si sovrappongano (utilizzata per i clash)
def isConflict(start_a, end_a, start_b, end_b):
    start = datetime.fromtimestamp(int(start_a))
    end = datetime.fromtimestamp(int(end_a))

    start_c = datetime.fromtimestamp(int(start_b))
    end_c = datetime.fromtimestamp(int(end_b))

    if datetime.date(start) >= datetime.date(start_c) and datetime.date(end) <= datetime.date(end_c):
        if datetime.time(start) >= datetime.time(start_c) and datetime.time(end) <= datetime.time(end_c):
            return True
    return False


# Funzione che verifica la presenza di clash, sia su stesso calendario, che su diverso calendario
def isThereAConflict(event_calendar, start, end, creator):
    owner = Connections.getCal().find_one({"_id": ObjectId(event_calendar)}, {"owner": 1, "_id": 0})
    clashed_event = {}
    # Si analizzano tutti gli eventi e se ne cerca uno (se esiste) che vada in clash con quello che si vuole
    # inserire/modificare
    if owner is not None:
        calendars = Connections.getCal().find({"owner": owner["owner"]})
        for calendar in calendars:
            for event in calendar["Events"]:
                event_to_check_with = Connections.getEvent().find_one({"_id": event})
                if event_to_check_with is not None:
                    if isConflict(start, end, event_to_check_with["start"], event_to_check_with["end"]):
                        clashed_event = event_to_check_with

    # Se ne esiste uno, controlla di che tipo di clash si tratta EVENTI CALENDARI DIVERSI: - Se il delegato fissa un
    # nuovo evento in un calendaro non esclusivo che va in clash con un evento già fissato di un calendario
    # esclusivo, non fisso il nuovo evento. - Se ho già fissato un evento in un calendario non esclusivo e sto
    # fissando un evento in un calendario esclusivo, nel caso di clash, lascio entrambi gli eventi - Se entrambi i
    # calendari sono non eslcusivi, allora lascio entrambi gli eventi memorizzati - Se i calendari sono entrambi
    # esclusivi, devo notificarlo all'utente e decide lui

    # EVENTI CALENDARI UGUALI: - Se ci sono eventi fissati da owner, antecedenti a quelli fissati da delegati,
    # vince quello owner ed evento delegato non viee fissato - Se viene fissato prima l'evento del delegato e poi
    # quello dell'owner, allora lascio fissati entrambi gli eventi - Stessa cosa vale per eventi fissati dal delegato
    # root rispetto ad eventi fissati dal delegato admin - Se viene fissato prima un evento da parte del delegato
    # root e poi da parte del delegato admin e vanno i clash, lascio fissato quello del delegato root - Viceversa
    # lascio fssati entrambi gli eventi - In caso di utenti paritari, quindi delegati root e delegati admin,
    # in ogni caso lascio fissati entrambi gli eventi in clash

    if len(clashed_event) != 0:
        if clashed_event["calendar"] == event_calendar:
            print("Clash sullo stesso calendario", event_calendar)
            if owner["owner"] == clashed_event["creator"]:
                return "F"

            delegate_new_event = Connections.getAdmin_Auth().find_one({"user_id": creator}, {"level": 1})
            delegate_old_event = Connections.getAdmin_Auth().find_one({"user_id": clashed_event["creator"]}, {"level": 1})
            if delegate_old_event["level"] == delegate_new_event["level"] or \
                    (delegate_new_event["level"] == "DELEGATO_ROOT" and delegate_old_event[
                        "level"] == "DELEGATO_ADMIN"):
                return "T"
            if delegate_old_event["level"] == "DELEGATO_ROOT" and delegate_new_event["level"] == "DELEGATO_ADMIN":
                return "F"
        else:
            complete_event_calendar = Connections.getCal().find_one({"_id": ObjectId(event_calendar)})
            complete_clash_event_calendar = Connections.getCal().find_one({"_id": ObjectId(clashed_event["calendar"])})
            print("Clash su calendari diversi", event_calendar, clashed_event["calendar"])
            if (complete_event_calendar["xor"] == "true" and complete_clash_event_calendar["xor"] == "false") or \
                    (complete_event_calendar["xor"] == "false" and complete_clash_event_calendar["xor"] == "false"):
                return "T"
            if complete_event_calendar["xor"] == "true" and complete_clash_event_calendar["xor"] == "true":
                Connections.getEvent().update_one({"_id": ObjectId(clashed_event["_id"])}, {"$set": {"color": "#ff2400"}})
                return "EX"
            if complete_event_calendar["xor"] == "false" and complete_clash_event_calendar["xor"] == "true":
                return "F"
    return "T"
