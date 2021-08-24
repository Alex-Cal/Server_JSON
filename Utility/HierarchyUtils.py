import networkx as nx
from matplotlib import pyplot as plt
from Utility import Connections

# Funzione che permette di convertire la gerarchia di Graph in una immagine png e di salvarla con l'id dell'utente
def save_image(G, id):
    pos = nx.spring_layout(G, seed=100)
    nx.draw(G, pos, with_labels=True, node_size=1500, font_size=10)
    plt.savefig(id + ".jpg")
    plt.close()


# Funzione che permette di generare la gerarchia associata ad un utente
def getG(id):
    query = {'owner': id}
    hier = Connections.getHier().find_one(query, {"Hier": 1, "_id": 0})
    G = nx.DiGraph()
    for a in hier["Hier"]:
        if a["belongsto"] != "":
            G.add_edge(a["node"], a["belongsto"])
    return G