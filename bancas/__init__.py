"""Registro dos adaptadores por banca."""
from bancas.cebraspe import Cebraspe
from bancas.fcc import Fcc
from bancas.cesgranrio import Cesgranrio
from bancas.vunesp import Vunesp
from bancas.idecan import Idecan
from bancas.aocp import Aocp
from bancas.ibfc import Ibfc

ADAPTADORES = {a.chave: a for a in (Cebraspe, Fcc, Cesgranrio, Vunesp, Idecan, Aocp, Ibfc)}
