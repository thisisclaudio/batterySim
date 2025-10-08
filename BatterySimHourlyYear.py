import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# ------------------- EINSTELLUNGEN -------------------
basis_pfad = "data"
datei = "energyData24Hourly.csv"

# Akkusimulationsparameter
max_akku_kapazitat = 15.0      # kWh
min_akku_kapazitat = max_akku_kapazitat * 0.1  # kWh (10%)
akku_wirkungsgrad_laden = 0.8
akku_wirkungsgrad_entladen = 0.9
max_lade_leistung = 10        # kW
max_entlade_leistung = 10     # kW
start_soc = 0.5               # Start mit 50 % Ladung

strompreis_bezug_rp = 22.5    # Rappen pro kWh für Bezug
einspeiseverg_rp = 7.5        # Rappen pro kWh für Einspeisung

# Liste der zu extrahierenden Sensoren
sensors = [
    'sensor.netznutzung_kwh',
    'sensor.netzeinspeisung_kwh',
    'sensor.sma_st_80_total_yield',
    'sensor.sn_3012091531_pv_gen_meter'
]

# ------------------- DATEN EINLESEN -------------------
# Lade die CSV-Datei
df = pd.read_csv(os.path.join(basis_pfad, datei))

# Konvertiere 'last_changed' zu datetime und stelle sicher, dass 'state' numerisch ist
df['last_changed'] = pd.to_datetime(df['last_changed'])
df['state'] = pd.to_numeric(df['state'], errors='coerce')

# Filtere Daten für das Jahr 2024
df = df[df['last_changed'].dt.year == 2024]

# Berechne stündliche Differenzen und speichere sie als Datenreihen
data_dict = {}
for sensor in sensors:
    df_sensor = df[df['entity_id'] == sensor].copy()
    if not df_sensor.empty:
        df_sensor = df_sensor.sort_values('last_changed')
        # Berechne stündliche Differenzen
        df_sensor['diff'] = df_sensor['state'].diff()
        # Entferne die erste Zeile, da die Differenz dort NaN ist
        df_sensor = df_sensor.dropna(subset=['diff'])
        # Speichere die Datenreihe (Zeitstempel als Index, Differenzen als Werte)
        data_dict[sensor] = df_sensor[['last_changed', 'diff']].set_index('last_changed')['diff']

# Erstelle einen DataFrame aus den stündlichen Differenzen
df_time = pd.DataFrame(data_dict)
df_time.index.name = 'Zeit'

# Auf 1-Stunden-Raster interpolieren
df_time = df_time.resample('1h').interpolate(method='linear')

# ------------------- DATEN AUFBEREITEN -------------------
# PV und Verbrauch berechnen
pv_west = df_time['sensor.sma_st_80_total_yield']
pv_ost = df_time['sensor.sn_3012091531_pv_gen_meter']
pv_sum = pv_ost + pv_west

netznutzung = df_time['sensor.netznutzung_kwh']
netzeinspeisung = df_time['sensor.netzeinspeisung_kwh']
hausverbrauch = pv_sum - netzeinspeisung + netznutzung

pv_sum = pv_ost + pv_west*1

pv_uebrig = pv_sum - hausverbrauch

# ------------------- AKKUSIMULATION -------------------
dates = df_time.index
simuAkku = np.zeros(len(dates))
akku_stand = max_akku_kapazitat * start_soc
zeitintervall = 1 / 60  # 1 Minute = 1/60 Stunden

for i in range(len(dates)):
    if pv_uebrig.iloc[i] > 0:
        # Ladeleistung in kW, begrenzt durch maximale Ladeleistung
        ladeleistung = min(pv_uebrig.iloc[i], max_lade_leistung)
        # Umrechnung in kWh unter Berücksichtigung des Wirkungsgrads
        ladeenergie = ladeleistung * akku_wirkungsgrad_laden * zeitintervall
        akku_stand = min(akku_stand + ladeenergie, max_akku_kapazitat)
    else:
        # Entladeleistung in kW, begrenzt durch maximale Entladeleistung
        entladeleistung = min(abs(pv_uebrig.iloc[i]), max_entlade_leistung)
        # Umrechnung in kWh unter Berücksichtigung des Wirkungsgrads
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

plt.title("Autarkieanalyse – Simulation 2024")
plt.ylabel("kWh")
plt.xlabel("Zeit")
plt.grid(True)
plt.legend()
plt.xticks(rotation=45)
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

# Autarkiegrad
verbrauch_deckt_durch_pv_und_akku = pv_direktnutzung_kwh + akku_entnahmen_kwh
autarkiegrad = (verbrauch_deckt_durch_pv_und_akku / gesamt_verbrauch_kwh) * 100

# Eingespare Energie
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
# Nettoersparnis durch Akku
ersparnis_durch_vermeidung_netbezug_rp = akku_entnahmen_kwh * strompreis_bezug_rp
verlust_durch_verhinderte_einspeisung_rp = akku_energie_von_pv_kwh * einspeiseverg_rp
netto_ersparnis_akku_rp = ersparnis_durch_vermeidung_netbezug_rp - verlust_durch_verhinderte_einspeisung_rp
netto_ersparnis_akku_chf = netto_ersparnis_akku_rp / 100

# Ausgabe
print("\n------------------- FINANZIELLE ERSPARNIS (AKKU) -------------------")
print(f"Netzstrom durch Akku vermieden:   {akku_entnahmen_kwh:.2f} kWh → {ersparnis_durch_vermeidung_netbezug_rp:.2f} Rp")
print(f"Verhinderte Einspeisung:          {akku_energie_von_pv_kwh:.2f} kWh → {verlust_durch_verhinderte_einspeisung_rp:.2f} Rp")
print(f"💰 Nettoersparnis durch Akku:     {netto_ersparnis_akku_chf:.2f} CHF")
print("----------------------------------------------------------------------")