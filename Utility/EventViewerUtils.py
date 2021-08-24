import HierarchyUtils
import AuthUtils

import pymongo
from bson import ObjectId

# Connection to MongoDB
import PreCondUtils
import Utils

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["CalendarDB"]
Cal = mydb["Calendar"]
Group = mydb["Group"]
Event = mydb["Events"]
Auth = mydb["Authorization"]
Admin_Auth = mydb["Admin_Auth"]


# Funzione che restituisce, dato utente e calendario, gli eventi visibili per quell'utente, considerando la sua
# posizione gerarchica e recuperando tutte le relative auth function_scope indica se si stanno valutando auth di
# write o read
def getVisibileEventsWithHier(user, calendar, function_scope):
    authorization_type_to_find = "write"
    if function_scope == "show":
        authorization_type_to_find = "read"
    # otteniamo proprietario del calendario e la sua relativa gerarchia
    owner_Cal = Cal.find_one({"_id": ObjectId(calendar)}, {"_id": 0, "owner": 1})
    G = HierarchyUtils.getG(owner_Cal["owner"])
    # otteniamo la lista dei gruppi a cui l'utente appartiene
    g_id = (Utils.user_to_group(user))
    group_name = []
    for group in g_id:
        group_name.append(Group.find_one({"_id": group}, {"_id": 0, "name": 1}))
    groups_auth = []
    no_event = False
    for group in group_name:
        n = group["name"]
        # ciclichiamo sul grafo alla ricerca di altre autorizzazioni, che verranno ereditate, partendo dal gruppo più
        # vicino all'utente
        # salviamo le autorizzazioni del gruppo più vicino all'utente e risolviamo conflitti, se ne esistono
        auth_for_group = Group.find_one({"name": n, "creator": owner_Cal["owner"]},
                                        {"_id": 0, "Authorization": 1})
        groups_auth.append((AuthUtils.filter_auth(auth_for_group, calendar, authorization_type_to_find)))
        while n != "ANY":
            for node in G.successors(n):
                n = node
                # salviamo le autorizzazioni dei gruppi più alti in gerarchia e risolviamo conflitti, se ne esistono
                auth_for_group = Group.find_one({"name": node, "creator": owner_Cal["owner"]},
                                                {"_id": 0, "Authorization": 1})
                groups_auth.append((AuthUtils.filter_auth(auth_for_group, calendar, authorization_type_to_find)))
        no_event = True

    for item in groups_auth:
        if len(item) != 0:
            no_event = False
    # Se non esistono eventi visualizzabili, ritorna lista vuota
    if no_event:
        return []

    events_evaluated = []
    # analizza tutti i segni delle autorizzazioni, per capire se sono concordi o discordi
    # print(groups_auth)
    for auth in groups_auth:
        if len(auth) != 0:
            events_group = []
            [positive_sign, negative_sign] = AuthUtils.checkSign(auth["Authorization"])
            for a in (auth["Authorization"]):
                events_group.append(AuthUtils.authorization_filter(a, calendar))
            # print(events_group)
            # if same sign = union; else, intersection
            if positive_sign:
                events_evaluated.append((Utils.create_set_union(events_group), "+"))
            else:
                events_evaluated.append((Utils.create_set_intersect(events_group), "-"))

    result = []
    for i in range(0, len(events_evaluated) - 1, 1):
        list_temp = [events_evaluated[i][0], events_evaluated[i + 1][0]]
        if events_evaluated[i][1] == "+":
            result = Utils.create_set_union(list_temp)
        else:
            result = Utils.create_set_intersect(list_temp)
        return result

    return events_evaluated[0][0]

    # Recuperiamo tutti i gruppi fino ad ANY, da G Ottenuti tutti i gruppi, è necessario recuperare tutte le
    # autorizzazioni associate a ogni gruppo Salviamo, quindi, tutti gli eventi visibili, autorizzazioni per
    # autorizzazione e, volta per volta, a seconda del tipo/segno uniamo o sottraiamo gli eventi


# Funzione che restituisce tutti gli eventi che un utente può scrivere (utilizzata nella modifica di un evento)
# N.B. Si basa sulla funzione getVisibileEventsWithHier
def eventUserCanWrite(user, calendar):
    user_group = Utils.user_to_group(user)
    events = getVisibileEventsWithHier(user, calendar, "update")
    result = []
    if len(events) != 0:
        if len(user_group) == 1:
            result = Group.find_one({"_id": user_group[0]}, {"Precondition": 1, "_id": 0})
            events = PreCondUtils.precond(result['Precondition'], events, calendar)
        else:
            for group in user_group:
                result = Group.find_one({"_id": group}, {"Precondition": 1, "_id": 0})
                events = PreCondUtils.precond(result['Precondition'], events, calendar)
        return events
    else:
        return []


# Funzione che fornisce la lista degli eventi che un delegato può visualizzare
def eventsADelegateCanRead(user_id, calendar_id):
    res = Admin_Auth.find_one({"user_id": user_id, "calendar_id": calendar_id})
    if res is None:
        print("Non si tratta di un delegato")
        return []
    events = Event.find({"calendar": calendar_id})
    if events is None:
        print("Sei un delegato, ma non ci sono eventi su questo calendario")
        return []
    list_events = []
    if res["repetition"] == "true":
        timeslot = res["startDay"] + "." + res["startHour"] + ":" + res["startMin"] + "-" + res["endDay"] + "." + res[
            "endHour"] + ":" + res["endMin"]
        list_events = PreCondUtils.evaluate_rep_admin(timeslot, events)
    else:
        timeslot = res["start"] + "-" + res["end"]
        list_events = PreCondUtils.evaluate_not_rep_admin(timeslot, events)

    event_create_by_delegate = Event.find({"creator": user_id, "calendar": calendar_id})
    for event in event_create_by_delegate:
        if not Utils.isInList(list_events, event, "_id", "_id"):
            list_events.append(event)
    return list_events