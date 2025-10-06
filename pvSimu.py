# -*- coding: utf-8 -*-
"""
Created on Fri Jul 25 10:15:14 2025

@author: Claud
"""

import pandas as pd
import matplotlib.pyplot as plt

# CSV einlesen
df = pd.read_csv("C:/Users/Claud/OneDrive/Dokumente/Python/pv/energy_y24.csv")
df.set_index("entity_id", inplace=True)
df.index = df.index.str.strip()  # <- hier Leerzeichen entfernen

# Zeitspalten
date_columns = df.columns[2:]
dates = pd.to_datetime(date_columns)




# PV-Daten
pv_west_ist = df.loc["sensor.sn_3012091531_pv_gen_meter", date_columns].astype(float)
pv_ost = df.loc["sensor.sma_st_80_pv_gen_meter", date_columns].astype(float)
pv_sum_ist = pv_ost + pv_west_ist
pv_west_wird = pv_west_ist * 6
pv_sum_wird = pv_ost + pv_west_wird




# Plot Vergleich PV Ertrag mit neuer Anlage
plt.figure(figsize=(12, 6))
plt.plot(dates, pv_west_ist, label="PV West Ist")
plt.plot(dates, pv_ost, label="PV Ost")
plt.plot(dates, pv_sum_ist, label="Gesamt Ist", linewidth=4)
plt.plot(dates, pv_west_wird, label="West Erweitert", linestyle="--", linewidth=2)
plt.plot(dates, pv_sum_wird, label="Gesamt Erweitert", linestyle="--", linewidth=4)
plt.title("Monatliche PV-Erzeugung")
plt.ylabel("kWh")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()




#Verbrauch Daten
netznutzung = df.loc["sensor.netznutzung_kwh", date_columns].astype(float)
netzeinspeisung = df.loc["sensor.netzeinspeisung_kwh", date_columns].astype(float)
hausverbrauch = pv_sum_ist - netzeinspeisung + netznutzung



pv_uebrig = pv_sum_ist - hausverbrauch


# Plot 2: PV-Gesamterzeugung ist mit Netznutzung und Netzeinspeisung
plt.figure(figsize=(12, 8))
#plt.plot(dates, pv_sum_ist, label="PV Gesamt Ist", linewidth=2)
#plt.plot(dates, netznutzung, label="Netznutzung", linestyle="-", linewidth=2, color="red")
#plt.plot(dates, netzeinspeisung, label="Netzeinspeisung", linestyle="-", linewidth=2)
plt.plot(dates, pv_sum_ist, label="PV Gesamt", linestyle="-", linewidth=2)
plt.plot(dates, hausverbrauch, label="Hausverbrauch", linewidth=2)
plt.plot(dates, pv_uebrig, label="PV Überschuss", linestyle="--", linewidth=2)
plt.title("Autarkieanalyse: Aktuelle PV-Anlage")
plt.ylabel("kWh")
plt.grid(True)
plt.legend()
plt.tight_layout()
# Markierung der Bereiche, wo pv_uebrig > 0 ist, mit präziser Interpolation
plt.fill_between(dates, pv_uebrig, 0, where=(pv_uebrig > 0), color='green', alpha=0.3, label="PV Überschuss > 0", interpolate=True)

plt.show()


#Erweitert
pv_uebrig = pv_sum_wird - hausverbrauch

# Plot 3: PV-Gesamterzeugung erweitert mit Netznutzung und Netzeinspeisung
plt.figure(figsize=(12, 8))
#plt.plot(dates, pv_sum_ist, label="PV Gesamt Ist", linewidth=2)
#plt.plot(dates, netznutzung, label="Netznutzung", linestyle="-", linewidth=2, color="red")
#plt.plot(dates, netzeinspeisung, label="Netzeinspeisung", linestyle="-", linewidth=2)
plt.plot(dates, pv_sum_wird, label="PV Gesamt Erweitert", linestyle="-", linewidth=2)
plt.plot(dates, hausverbrauch, label="Hausverbrauch", linewidth=2)
plt.plot(dates, pv_uebrig, label="PV Überschuss", linestyle="--", linewidth=2)
plt.title("Autarkieanalyse: Erweiterte PV-Anlage")
plt.ylabel("kWh")
plt.grid(True)
plt.legend()
plt.tight_layout()
# Markierung der Bereiche, wo pv_uebrig > 0 ist, mit präziser Interpolation
plt.fill_between(dates, pv_uebrig, 0, where=(pv_uebrig > 0), color='green', alpha=0.3, label="PV Überschuss > 0", interpolate=True)

plt.show()

