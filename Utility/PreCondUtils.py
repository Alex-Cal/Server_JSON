from datetime import datetime
import StringUtils
import pymongo

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Precondition = mydb["Temporal Pre-Condition"]
Admin_Auth = mydb["Admin_Auth"]

# Funzione di utilità per le autorizzazioni amministrative (delegato) che restituisce gli eventi che soddisfano il
# timeslot indicato dalla auth amministrativa (di tipo non ripetizione) N.B. Vengono restuiti gli eventi che
# soddisfano il timeslot
def evaluate_not_rep_admin(timeslot, events):
    [start_date, start_hour, end_date, end_hour] = StringUtils.string_not_repetition(timeslot)
    good_event = []
    for item in events:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        if (datetime.date(start)) >= start_date and (datetime.date(end)) <= end_date:
            if datetime.time(start) >= start_hour and datetime.time(end) <= end_hour:
                good_event.append(item)
    return good_event


# Funzione di utilità per le autorizzazioni amministrative (delegato) che restituisce gli eventi che soddisfano il
# timeslot indicato dalla auth amministrativa (di tipo ripetizione) N.B. Vengono restuiti gli eventi che soddisfano
# il timeslot
def evaluate_rep_admin(timeslot, events):
    [start_day, start_hour, end_day, end_hour] = StringUtils.string_repetition(timeslot)
    good_event = []
    for item in events:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        start_hour_adm = datetime.strptime(start_hour, "%H:%M").time()
        end_hour_adm = datetime.strptime(end_hour, "%H:%M").time()
        if int(datetime.weekday(start)) >= int(start_day) and int(datetime.weekday(end)) <= int(end_day):
            if datetime.time(start) >= start_hour_adm and datetime.time(end) <= end_hour_adm:
                good_event.append(item)
    return good_event


# Funzione di utilità per le precondizioni temporali che restituisce gli eventi che soddisfano il timeslot indicato
# dalla precondizione (di tipo non ripetizione) N.B. Vengono restuiti gli eventi che non soddisfano il timeslot
def evaluate_not_rep(timeslot, eventi):
    [start_date, start_hour, end_date, end_hour] = StringUtils.string_not_repetition(timeslot)
    good_event = []
    for item in eventi:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        if datetime.date(start) > end_date or datetime.date(end) < start_date:
            good_event.append(item)
        elif datetime.time(start) > end_hour or datetime.time(end) < start_hour:
            good_event.append(item)
    return good_event


# Funzione di utilità per le precondizioni temporali che restituisce gli eventi che soddisfano il timeslot indicato
# dalla precondizione (di tipo ripetizione) N.B. Vengono restuiti gli eventi che non soddisfano il timeslot
def evaluate_rep(timeslot, eventi):
    [start_day, start_hour, end_day, end_hour] = StringUtils.string_repetition(timeslot)
    good_event = []
    for item in eventi:
        start = datetime.fromtimestamp(int(item["start"]))
        end = datetime.fromtimestamp(int(item["end"]))
        start_hour_pre = datetime.strptime(start_hour, "%H:%M").time()
        end_hour_pre = datetime.strptime(end_hour, "%H:%M").time()

        if int(datetime.weekday(start)) > int(end_day) or int(datetime.weekday(end)) < int(start_day):
            good_event.append(item)
        elif datetime.time(start) > end_hour_pre or datetime.time(end) < start_hour_pre:
            good_event.append(item)
    return good_event


# Funzione di wrapper che filtra gli eventi in base alle precondizioni esistenti
def precond(pre, eventi, calendar):
    for i in pre:
        timeslot = Precondition.find_one({"_id": i, "calendar_id": calendar})
        if timeslot is None:
            return eventi
        if timeslot["repetition"] == "true":
            return evaluate_rep(timeslot['timeslot'], eventi)
        else:
            return evaluate_not_rep(timeslot['timeslot'], eventi)
    return eventi

# Funzione di wrapper che filtra gli eventi in base alle autorizzazioni amministrative esistenti
def auth_adm(auth, query):
    for i in auth:
        timeslot = Admin_Auth.find_one({"_id": i},
                                       {"timeslot": 1, "_id": 0, "type_time": 1})
        if timeslot["type_time"] == "repetition":
            return evaluate_rep_admin(timeslot['timeslot'], query['calendar'])

        else:
            return evaluate_not_rep_admin(timeslot['timeslot'], query['calendar'])

# Funzione di utils che, fornito un utente, un calendario e un timeslot, restituisce True se l'utente può inserire in
# quel determinato timeslot
def canADelegateAccessTimeslot(user_id, calendar_id, start_time_to_insert, end_time_to_insert):
    admin_pre = Admin_Auth.find_one({"user_id": user_id, "calendar_id": calendar_id})
    if admin_pre is not None:
        start = datetime.fromtimestamp(int(start_time_to_insert))
        end = datetime.fromtimestamp(int(end_time_to_insert))
        # Individuata la auth di delegato, si controlla il timeslot su cui si applica e si effettua la valutazione
        # Se repetition == false, allora il timeslot è della forma start-end (in UnixTimestamp format)
        if admin_pre["repetition"] == "false":
            timeslot = admin_pre["start"] + "-" + admin_pre["end"]
            [start_date, start_hour, end_date, end_hour] = StringUtils.string_not_repetition(timeslot)
            if (datetime.date(start)) >= start_date and (datetime.date(end)) <= end_date:
                if datetime.time(start) >= start_hour and datetime.time(end) <= end_hour:
                    return True
            return False
        else:
            # Se repetition == true, allora il timeslot è della forma startDay.startHour-endDay.endHour dove startDay
            # e endDay
            timeslot = admin_pre["startDay"] + "." + admin_pre["startHour"] + ":" + admin_pre["startMin"] + "-" + \
                       admin_pre["endDay"] + "." + admin_pre["endHour"] + ":" + admin_pre["endMin"]
            [start_day, start_hour, end_day, end_hour] = StringUtils.string_repetition(timeslot)
            start_hour_adm = datetime.strptime(start_hour, "%H:%M").time()
            end_hour_adm = datetime.strptime(end_hour, "%H:%M").time()
            if int(datetime.weekday(start)) >= int(start_day) and int(datetime.weekday(end)) <= int(end_day):
                if datetime.time(start) >= start_hour_adm and datetime.time(end) <= end_hour_adm:
                    return True
        return False
    return False