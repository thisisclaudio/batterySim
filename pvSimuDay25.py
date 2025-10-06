# -*- coding: utf-8 -*-
"""
Created on Fri Jul 25 11:16:34 2025

@author: Claud
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# CSV einlesen
df = pd.read_csv("data\energy_september1_25.csv")
df.set_index("entity_id", inplace=True)
df.index = df.index.str.strip()  # <- hier Leerzeichen entfernen

# Zeitspalten
date_columns = df.columns[2:]
dates = pd.to_datetime(date_columns)

# PV-Daten
pv_west = df.loc["sensor.sungrow_sg12rt_total_yield", date_columns].astype(float)
pv_ost = df.loc["sensor.sma_st_80_pv_gen_meter", date_columns].astype(float)
pv_sum = pv_ost + pv_west

# Verbrauch Daten
netznutzung = df.loc["sensor.netznutzung_kwh", date_columns].astype(float)
netzeinspeisung = df.loc["sensor.netzeinspeisung_kwh", date_columns].astype(float)
hausverbrauch = pv_sum - netzeinspeisung + netznutzung

pv_uebrig = pv_sum - hausverbrauch

# Plot 2: PV-Gesamterzeugung ist mit Netznutzung und Netzeinspeisung
plt.figure(figsize=(12, 8))
plt.plot(dates, pv_sum, label="PV Gesamt", linestyle="-", linewidth=2)
plt.plot(dates, hausverbrauch, label="Hausverbrauch", linewidth=2)
plt.plot(dates, pv_uebrig, label="PV Überschuss", linestyle="--", linewidth=2)

# Berechnung des Integrals (kumulative Summe) des Hausverbrauchs
integral_hausverbrauch = np.cumsum(hausverbrauch)
#plt.plot(dates, integral_hausverbrauch, label="Kumulierter Hausverbrauch", linestyle="-.", linewidth=2)

# Berechnung des Integrals des PV Überschusses (conditional >0)
conditional_pv_uebrig = pv_uebrig.copy()
conditional_pv_uebrig[pv_uebrig <= 0] = 0
integral_pv_uebrig = np.cumsum(conditional_pv_uebrig)
#plt.plot(dates, integral_pv_uebrig, label="Kumulierter PV Überschuss", linestyle="-.", linewidth=2)

# Parameter für Akkusimulation
max_akku_kapazitat = 20.0  # Maximale Akkukapazität in kWh
min_akku_kapazitat = max_akku_kapazitat * 0.1  # Minimale Akkukapazität (10%)
akku_wirkungsgrad_laden = 0.8  # Wirkungsgrad beim Laden
akku_wirkungsgrad_entladen = 0.9  # Wirkungsgrad beim Entladen
max_lade_leistung = 3.0    # Maximale Ladeleistung in kW pro Stunde
max_entlade_leistung = 3.0 # Maximale Entladeleistung in kW pro Stunde
soc_start = 0.5  # Start-SOC (State of Charge) in Prozent (50%)


# Initialisierung
simuAkku = np.zeros(len(dates))
aktueller_akku_stand = max_akku_kapazitat * soc_start  # Start mit 50% Ladung

for i in range(len(dates)):
    if pv_uebrig.iloc[i] > 0:
        # Akku laden mit Wirkungsgrad und Ladeleistungsbegrenzung
        ladeenergie = min(pv_uebrig.iloc[i] * akku_wirkungsgrad_laden, max_lade_leistung)
        aktueller_akku_stand = min(aktueller_akku_stand + ladeenergie, max_akku_kapazitat)
    else:
        # Akku entladen für Hausverbrauch mit Entladeleistungsbegrenzung
        fehlende_energie = min(abs(pv_uebrig.iloc[i]) / akku_wirkungsgrad_entladen, max_entlade_leistung)
        aktueller_akku_stand = max(aktueller_akku_stand - fehlende_energie, min_akku_kapazitat)
    
    simuAkku[i] = aktueller_akku_stand

plt.plot(dates, simuAkku, label="Simu Akku Ladestand", linestyle="-.", linewidth=2)

plt.title("Autarkieanalyse: Aktuelle PV-Anlage")
plt.ylabel("kWh")
plt.grid(True)
plt.legend()
plt.tight_layout()
# Markierung der Bereiche, wo pv_uebrig > 0 ist, mit präziser Interpolation
plt.fill_between(dates, pv_uebrig, 0, where=(pv_uebrig > 0), color='green', alpha=0.3, label="PV Überschuss > 0", interpolate=True)

plt.show()