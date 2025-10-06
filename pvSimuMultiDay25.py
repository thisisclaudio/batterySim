# -*- coding: utf-8 -*-
"""
PV- und Akku-Simulation über mehrere Tagesdateien

Erstellt: 2025-07-25
Autor: Claud
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# ------------------- EINSTELLUNGEN -------------------

basis_pfad = "data"
tage = range(1, 31)  # Welche Tage einlesen -> 1 bis 30
datei_template = "energy_september{}_25.csv"

# Akkusimulationsparameter
max_akku_kapazitat = 15.0      # kWh
min_akku_kapazitat = max_akku_kapazitat * 0.1  # kWh (10%)
akku_wirkungsgrad_laden = 0.8
akku_wirkungsgrad_entladen = 0.9
max_lade_leistung = 10        # kW
max_entlade_leistung = 10     # kW
start_soc = 0.5                # Start mit 50 % Ladung

# ------------------- DATEN EINLESEN -------------------

dfs = []
for tag in tage:
    datei = os.path.join(basis_pfad, datei_template.format(tag))
    if not os.path.exists(datei):
        print(f"⚠️ Datei nicht gefunden: {datei}")
        continue
    df_temp = pd.read_csv(datei)
    df_temp.set_index("entity_id", inplace=True)
    df_temp.index = df_temp.index.str.strip()
    dfs.append(df_temp)

if not dfs:
    raise FileNotFoundError("Keine gültigen CSV-Dateien gefunden.")

# Zeitlich zusammenfügen
df = pd.concat(dfs, axis=1)



# --- Diagnose robust ---
import numpy as np
import pandas as pd

# Nur Zeitspalten (die mit einer Zahl anfangen)
date_columns = [c for c in df.columns if c[:4].isdigit()]

# In echte Timestamps konvertieren
dates = pd.to_datetime(date_columns, errors="coerce", infer_datetime_format=True)

# NaT (ungültige) Einträge entfernen
dates = dates.dropna()
dates_sorted = np.sort(dates.values.astype("datetime64[ns]"))

# Zeitabstände in Minuten berechnen
delta = np.diff(dates_sorted).astype('timedelta64[m]').astype(int)

gaps = np.where(delta > 10)[0]

print(f"Gesamtanzahl Spalten: {len(df.columns)}")
print(f"Erkannte Zeitspalten: {len(date_columns)}")
if len(gaps):
    print(f"⚠️ Es gibt {len(gaps)} Zeitlücken über 10 Minuten:")
    for g in gaps:
        print(f"  {dates_sorted[g]} → {dates_sorted[g+1]}  (Δ {delta[g]} min)")
else:
    print("✅ Keine signifikanten Zeitlücken erkannt.")




# ------------------- DATEN AUFBEREITEN -------------------

# Nur Zeitspalten erkennen
date_columns = [c for c in df.columns if c[:4].isdigit()]

# In echte Timestamps konvertieren
dates = pd.to_datetime(date_columns, errors="coerce")
dates = dates.dropna()

# --- Lücken auffüllen ---
# DataFrame nur auf Zeitspalten reduzieren
df_time = df[date_columns].copy()

# Spaltennamen auf Zeitindex setzen
df_time.columns = dates
df_time = df_time.T  # Spalten → Zeilen für resample
df_time.index.name = 'Zeit'

# Auf 1-Minuten-Raster bringen und linear interpolieren
df_time = df_time.resample('1min').interpolate(method='linear')

# Zurücktransponieren, damit Berechnungen wie bisher funktionieren
df_time = df_time.T
date_columns = df_time.columns
dates = date_columns

# --- PV und Verbrauch auf interpolierten Daten ---
pv_west = df_time.loc["sensor.sungrow_sg12rt_total_yield"].astype(float)
pv_ost = df_time.loc["sensor.sma_st_80_pv_gen_meter"].astype(float)
pv_sum = pv_ost + pv_west

netznutzung = df_time.loc["sensor.netznutzung_kwh"].astype(float)
netzeinspeisung = df_time.loc["sensor.netzeinspeisung_kwh"].astype(float)
hausverbrauch = pv_sum - netzeinspeisung + netznutzung

pv_uebrig = pv_sum - hausverbrauch

# ------------------- AKKUSIMULATION -------------------

simuAkku = np.zeros(len(dates))
akku_stand = max_akku_kapazitat * start_soc

zeitintervall = 1 / 60  # ⬅️ HIER: 1 Minute = 1/60 Stunden (für kWh-Umrechnung)

for i in range(len(dates)):
    if pv_uebrig.iloc[i] > 0:
        # Ladeleistung in kW, begrenzt durch maximale Ladeleistung
        ladeleistung = min(pv_uebrig.iloc[i], max_lade_leistung)
        # Umrechnung in kWh unter Berücksichtigung des Wirkungsgrads und Zeitintervalls
        ladeenergie = ladeleistung * akku_wirkungsgrad_laden * zeitintervall
        akku_stand = min(akku_stand + ladeenergie, max_akku_kapazitat)
    else:
        # Entladeleistung in kW, begrenzt durch maximale Entladeleistung
        entladeleistung = min(abs(pv_uebrig.iloc[i]), max_entlade_leistung)
        # Umrechnung in kWh unter Berücksichtigung des Wirkungsgrads und Zeitintervalls
        entladeenergie = entladeleistung / akku_wirkungsgrad_entladen * zeitintervall
        akku_stand = max(akku_stand - entladeenergie, min_akku_kapazitat)
    
    simuAkku[i] = akku_stand

# ------------------- PLOTTEN -------------------

plt.figure(figsize=(14, 8))
plt.plot(dates, pv_sum, label="PV Gesamt", linewidth=2)
plt.plot(dates, hausverbrauch, label="Hausverbrauch", linewidth=2)
plt.plot(dates, pv_uebrig, label="PV Überschuss", linestyle="--", linewidth=2)
plt.plot(dates, simuAkku, label="Simu Akku Ladestand", linestyle="-.", linewidth=2)
plt.fill_between(dates, pv_uebrig, 0, where=(pv_uebrig > 0),
                 color='green', alpha=0.3, label="PV Überschuss > 0", interpolate=True)

plt.title("Autarkieanalyse – Mehrtagessimulation")
plt.ylabel("kWh")
plt.xlabel("Zeit")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()


# ------------------- SUMMARY-BERECHNUNG -------------------

# Gesamtverbrauch (Haus) in kWh über den Zeitraum
gesamt_verbrauch_kwh = hausverbrauch.sum() * zeitintervall

# Gesamt-PV-Produktion
gesamt_pv_kwh = pv_sum.sum() * zeitintervall

# PV direkt genutzt (nicht eingespeist)
pv_direktnutzung_kwh = hausverbrauch.where(pv_sum >= hausverbrauch, pv_sum).sum() * zeitintervall

# PV-Energie, die in den Akku geladen wurde
akku_ladungen_kwh = np.diff(simuAkku, prepend=simuAkku[0])
akku_energie_von_pv_kwh = akku_ladungen_kwh[akku_ladungen_kwh > 0].sum()

# PV-Energie, die aus dem Akku entnommen wurde
akku_entnahmen_kwh = -akku_ladungen_kwh[akku_ladungen_kwh < 0].sum()

# Gesamt-Netzbezug (laut Sensor)
netzbezug_kwh = netznutzung.sum() * zeitintervall

# Autarkiegrad (wie viel % des Verbrauchs durch PV + Akku gedeckt wurde)
verbrauch_deckt_durch_pv_und_akku = pv_direktnutzung_kwh + akku_entnahmen_kwh
autarkiegrad = (verbrauch_deckt_durch_pv_und_akku / gesamt_verbrauch_kwh) * 100

# Einfache Einsparung: was du nicht aus dem Netz holen musstest
eingespart_kwh = verbrauch_deckt_durch_pv_und_akku

# Ausgabe
print("\n------------------- ENERGIE-SUMMARY -------------------")
print(f"Gesamtverbrauch:         {gesamt_verbrauch_kwh:.2f} kWh")
print(f"PV-Gesamterzeugung:      {gesamt_pv_kwh:.2f} kWh")
print(f"Direkt genutzte PV:      {pv_direktnutzung_kwh:.2f} kWh")
print(f"Energie in Akku geladen: {akku_energie_von_pv_kwh:.2f} kWh")
print(f"Aus dem Akku entnommen:  {akku_entnahmen_kwh:.2f} kWh")
print(f"Netzbezug:               {netzbezug_kwh:.2f} kWh")
print(f"Gesparte Energie (PV+Akku): {eingespart_kwh:.2f} kWh")
print(f"Autarkiegrad:            {autarkiegrad:.1f} %")
print("--------------------------------------------------------")


# ------------------- AKKU-ERSARNIS IN CHF -------------------

strompreis_bezug_rp = 22.5   # Rappen pro kWh für Bezug
einspeiseverg_rp = 7.5       # Rappen pro kWh für Einspeisung

# Was der Akku an Netzstrom spart (in Rappen)
ersparnis_durch_vermeidung_netbezug_rp = akku_entnahmen_kwh * strompreis_bezug_rp

# Was man "verliert", weil man weniger einspeist (in Rappen)
verlust_durch_verhinderte_einspeisung_rp = akku_energie_von_pv_kwh * einspeiseverg_rp

# Nettoersparnis durch Akku (in Rappen)
netto_ersparnis_akku_rp = ersparnis_durch_vermeidung_netbezug_rp - verlust_durch_verhinderte_einspeisung_rp

# Umrechnung in CHF
netto_ersparnis_akku_chf = netto_ersparnis_akku_rp / 100

# Ausgabe
print("\n------------------- FINANZIELLE ERSPARNIS (AKKU) -------------------")
print(f"Netzstrom durch Akku vermieden:   {akku_entnahmen_kwh:.2f} kWh → {ersparnis_durch_vermeidung_netbezug_rp:.2f} Rp")
print(f"Verhinderte Einspeisung:          {akku_energie_von_pv_kwh:.2f} kWh → {verlust_durch_verhinderte_einspeisung_rp:.2f} Rp")
print(f"💰 Nettoersparnis durch Akku:     {netto_ersparnis_akku_chf:.2f} CHF")
print("----------------------------------------------------------------------")



# ------------------- ENDE -------------------