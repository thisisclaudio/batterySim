import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import uuid

# Definierte Pfade und Sensoren
basis_pfad = "data"
datei = "energyData24Hourly.csv"
full_path = f"{basis_pfad}/{datei}"

# CSV laden
df = pd.read_csv(full_path)

# Zeitstempel in datetime umwandeln (UTC, wie in den Daten)
df['last_changed'] = pd.to_datetime(df['last_changed'])

# Liste der Sensoren
sensors = [
    'sensor.netznutzung_kwh',
    'sensor.netzeinspeisung_kwh',
    'sensor.sma_st_80_total_yield',
    'sensor.sn_3012091531_pv_gen_meter'
]

# Dictionary zum Speichern der separaten Datenreihen
data_series = {}

# Erstelle einen vollständigen Zeitindex (stündlich für das ganze Jahr 2024)
start_time = pd.Timestamp('2024-01-01 00:00:00', tz='UTC')
end_time = pd.Timestamp('2024-12-31 23:00:00', tz='UTC')
full_time_index = pd.date_range(start=start_time, end=end_time, freq='h')

for sensor in sensors:
    df_sensor = df[df['entity_id'] == sensor].copy()
    df_sensor.sort_values('last_changed', inplace=True)
    df_sensor['hourly_diff'] = df_sensor['state'].diff()
    df_sensor.dropna(subset=['hourly_diff'], inplace=True)
    
    # Filtere nur 2024 Daten
    df_sensor = df_sensor[df_sensor['last_changed'].dt.year == 2024]
    
    # Erstelle einen DataFrame mit dem vollständigen Zeitindex
    df_complete = pd.DataFrame(index=full_time_index)
    df_complete['hourly_diff'] = 0.0  # Standardwert 0
    
    # Setze die vorhandenen Werte
    df_sensor_indexed = df_sensor.set_index('last_changed')
    
    # Für PV-Sensoren: Runde Zeitstempel auf die nächste Stunde und fülle mit 0
    if 'sma_st_80' in sensor or 'sn_3012091531' in sensor:
        df_sensor_indexed.index = df_sensor_indexed.index.round('h')
        df_sensor_indexed = df_sensor_indexed.groupby(df_sensor_indexed.index).first()
        common_index = df_sensor_indexed.index.intersection(df_complete.index)
        df_complete.loc[common_index, 'hourly_diff'] = df_sensor_indexed.loc[common_index, 'hourly_diff']
    else:
        df_sensor_indexed.index = df_sensor_indexed.index.round('h')
        df_sensor_indexed = df_sensor_indexed.groupby(df_sensor_indexed.index).first()
        common_index = df_sensor_indexed.index.intersection(df_complete.index)
        df_complete.loc[common_index, 'hourly_diff'] = df_sensor_indexed.loc[common_index, 'hourly_diff']
    
    data_series[sensor] = df_complete

# Zeige Statistiken für jeden Sensor
for sensor, ds in data_series.items():
    non_zero_count = (ds['hourly_diff'] != 0).sum()
    total_count = len(ds)
    print(f"\n{sensor}:")
    print(f"  Datenpunkte mit Werten > 0: {non_zero_count}/{total_count}")
    print(f"  Erste 5 Nicht-Null Werte:")
    print(ds[ds['hourly_diff'] != 0].head())

# Erstelle einen kombinierten DataFrame für Berechnungen
combined_df = pd.DataFrame(index=full_time_index)

for sensor_name, ds in data_series.items():
    combined_df[sensor_name] = ds['hourly_diff']

# Berechne PV gesamt (sma_st_80_total_yield + sn_3012091531_pv_gen_meter)
combined_df['pv_gesamt_kwh'] = (combined_df['sensor.sma_st_80_total_yield'] + 
                               combined_df['sensor.sn_3012091531_pv_gen_meter'])

# Berechne den Hausverbrauch für jede Stunde
combined_df['hausverbrauch_kwh'] = (combined_df['pv_gesamt_kwh'] - 
                                   combined_df['sensor.netzeinspeisung_kwh'] + 
                                   combined_df['sensor.netznutzung_kwh'])

# Erweitere PV Erträge mit dem Faktor 6 für West Anlage
combined_df['sensor.sn_3012091531_pv_gen_meter_erweitert'] = combined_df['sensor.sn_3012091531_pv_gen_meter'] * 6

# Berechne den PV Gesamt mit der erweiterten West Anlage
combined_df['pv_gesamt_kwh_erweitert'] = (combined_df['sensor.sma_st_80_total_yield'] + 
                                         combined_df['sensor.sn_3012091531_pv_gen_meter_erweitert'])

# Berechne den PV Überschuss
combined_df['pv_uebrig_kwh'] = combined_df['pv_gesamt_kwh_erweitert'] - combined_df['hausverbrauch_kwh']

# ------------------- AKKUSIMULATION -------------------

# Akku-Parameter
max_akku_kapazitat = 20.0  # kWh
start_soc = 0.5  # Start State of Charge (50%)
min_akku_kapazitat = max_akku_kapazitat * 0.1  # Minimum 10% der Kapazität
max_lade_leistung = 3.0  # kW
max_entlade_leistung = 3.0  # kW
akku_wirkungsgrad_laden = 0.95  # 95% Wirkungsgrad beim Laden
akku_wirkungsgrad_entladen = 0.95  # 95% Wirkungsgrad beim Entladen
zeitintervall = 1.0  # Stündliche Daten (1 Stunde)

# Akku-Simulation (korrigiert)
simuAkku = np.zeros(len(combined_df))
akku_stand = max_akku_kapazitat * start_soc

for i in range(len(combined_df)):
    pv_ueberschuss = combined_df['pv_uebrig_kwh'].iloc[i]
    
    if pv_ueberschuss > 0:  # PV-Überschuss vorhanden - Akku laden
        # Maximale Ladeenergie basierend auf verfügbarem Platz im Akku
        verfuegbarer_platz = max_akku_kapazitat - akku_stand
        # Begrenze auf maximale Ladeleistung und verfügbaren PV-Überschuss
        ladeenergie_brutto = min(pv_ueberschuss, max_lade_leistung * zeitintervall)
        # Berücksichtige Wirkungsgrad und verfügbaren Platz
        ladeenergie_netto = min(ladeenergie_brutto * akku_wirkungsgrad_laden, verfuegbarer_platz)
        akku_stand += ladeenergie_netto
        
    elif pv_ueberschuss < 0:  # PV-Defizit - Akku entladen
        # Benötigte Energie aus dem Akku
        benoetigte_energie = abs(pv_ueberschuss)
        # Verfügbare Energie im Akku (über Minimum)
        verfuegbare_energie = max(0, akku_stand - min_akku_kapazitat)
        # Begrenze auf maximale Entladeleistung
        max_entladeenergie = min(max_entlade_leistung * zeitintervall, verfuegbare_energie)
        # Tatsächliche Entladung (berücksichtige Wirkungsgrad)
        entladeenergie_netto = min(benoetigte_energie, max_entladeenergie)
        akku_stand -= entladeenergie_netto
        
    # Sicherheitscheck: Akku darf nie unter Minimum oder über Maximum
    akku_stand = max(min_akku_kapazitat, min(akku_stand, max_akku_kapazitat))
    simuAkku[i] = akku_stand

# Füge Akku-Stand dem DataFrame hinzu
combined_df['simu_akku_kwh'] = simuAkku



# Konvertiere Index zu timezone-naive
combined_df.index = combined_df.index.tz_localize(None)







# ------------------- PLOTTEN -------------------
"""
plt.figure(figsize=(20, 16))  # Größere Figur für 5 Subplots

# Subplot 1: Monatliche Summen
plt.subplot(3, 2, 1)
monthly_sums = combined_df.resample('M').sum()
months = monthly_sums.index.month
plt.bar(months, monthly_sums['pv_gesamt_kwh_erweitert'], alpha=0.7, label='PV Gesamt erweitert (kWh)')
plt.bar(months, monthly_sums['hausverbrauch_kwh'], alpha=0.7, label='Hausverbrauch (kWh)')
plt.bar(months, monthly_sums['pv_uebrig_kwh'], alpha=0.7, label='PV Überschuss (kWh)')
plt.xlabel('Monat')
plt.ylabel('kWh')
plt.title('Monatliche Energiesummen 2024')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(range(1, 13))

# Subplot 2: Tägliche Mittelwerte pro Monat
plt.subplot(3, 2, 2)
daily_avg = combined_df.resample('D').sum().resample('M').mean()
plt.plot(months, daily_avg['pv_gesamt_kwh_erweitert'], marker='o', label='PV Gesamt erweitert (kWh/Tag)', linewidth=2)
plt.plot(months, daily_avg['hausverbrauch_kwh'], marker='s', label='Hausverbrauch (kWh/Tag)', linewidth=2)
plt.plot(months, daily_avg['pv_uebrig_kwh'], marker='^', label='PV Überschuss (kWh/Tag)', linewidth=2)
plt.plot(months, daily_avg['simu_akku_kwh'], marker='d', label='Akku Ladestand (kWh)', linestyle='-.', linewidth=2)
plt.xlabel('Monat')
plt.ylabel('kWh/Tag')
plt.title('Durchschnittliche tägliche Energiewerte pro Monat')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(range(1, 13))

# Subplot 3: Wöchentliche Mittelwerte über das Jahr
plt.subplot(3, 2, 3)
weekly_avg = combined_df.resample('W').sum()
plt.plot(weekly_avg.index, weekly_avg['pv_gesamt_kwh_erweitert'], label='PV Gesamt erweitert (kWh/Woche)', linewidth=2)
plt.plot(weekly_avg.index, weekly_avg['hausverbrauch_kwh'], label='Hausverbrauch (kWh/Woche)', linewidth=2)
plt.plot(weekly_avg.index, weekly_avg['pv_uebrig_kwh'], label='PV Überschuss (kWh/Woche)', linewidth=2)
plt.plot(weekly_avg.index, weekly_avg['simu_akku_kwh'], label='Akku Ladestand (kWh)', linestyle='-.', linewidth=2)
plt.xlabel('Datum')
plt.ylabel('kWh/Woche')
plt.title('Wöchentliche Energiesummen 2024')
plt.legend()
plt.grid(True, alpha=0.3)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(rotation=45)

# Subplot 4: Tägliche Summen über das Jahr (kompakt)
plt.subplot(3, 2, 4)
daily_sums = combined_df.resample('D').sum()
plt.plot(daily_sums.index, daily_sums['pv_gesamt_kwh_erweitert'], alpha=0.7, label='PV Gesamt erweitert (kWh/Tag)')
plt.plot(daily_sums.index, daily_sums['hausverbrauch_kwh'], alpha=0.7, label='Hausverbrauch (kWh/Tag)')
plt.plot(daily_sums.index, daily_sums['simu_akku_kwh'], label='Akku Ladestand (kWh)', linestyle='-.', linewidth=2)
plt.fill_between(daily_sums.index, 0, daily_sums['pv_uebrig_kwh'], 
                 where=(daily_sums['pv_uebrig_kwh'] > 0), alpha=0.3, color='green', 
                 label='PV Überschuss (kWh/Tag)')
plt.fill_between(daily_sums.index, 0, daily_sums['pv_uebrig_kwh'], 
                 where=(daily_sums['pv_uebrig_kwh'] < 0), alpha=0.3, color='red', 
                 label='PV Defizit (kWh/Tag)')
plt.xlabel('Datum')
plt.ylabel('kWh/Tag')
plt.title('Tägliche Energiebilanz 2024')
plt.legend()
plt.grid(True, alpha=0.3)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(rotation=45)



# Subplot 5: Akku-Performance (stündlicher Ladestand über das ganze Jahr)
plt.subplot(3, 1, 3)
"""


# Erstelle einen längeren Plot für bessere Darstellung
plt.figure(figsize=(24, 10))

# Erste y-Achse: Alle Werte in kWh
color1 = 'tab:blue'
color2 = 'tab:green'
color3 = 'tab:orange'

plt.xlabel('Datum')
plt.ylabel('Energie (kWh)')
plt.plot(combined_df.index, combined_df['simu_akku_kwh'], linewidth=1.5, color=color1, alpha=0.8, label='Akku-Ladestand')
plt.plot(combined_df.index, combined_df['hausverbrauch_kwh'], linewidth=0.8, color=color2, alpha=0.6, label='Hausverbrauch')
plt.plot(combined_df.index, combined_df['pv_gesamt_kwh_erweitert'], linewidth=0.8, color=color3, alpha=0.6, label='PV-Erzeugung erweitert')

# Akku-Kapazitätsgrenzen
plt.axhline(y=max_akku_kapazitat, color='red', linestyle='--', alpha=0.7, label=f'Max. Kapazität ({max_akku_kapazitat} kWh)')
plt.axhline(y=min_akku_kapazitat, color='orange', linestyle='--', alpha=0.7, label=f'Min. Kapazität ({min_akku_kapazitat:.1f} kWh)')
plt.axhline(y=max_akku_kapazitat * 0.5, color='green', linestyle=':', alpha=0.5, label='50% Kapazität')

# Füllung unter Akku-Kurve
plt.fill_between(combined_df.index, min_akku_kapazitat, combined_df['simu_akku_kwh'], alpha=0.2, color=color1)

plt.grid(True, alpha=0.3)

# Formatierung der x-Achse
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(rotation=45)

# Titel und Legende
plt.title('Akku-Performance: Ladestand, Hausverbrauch und PV-Erzeugung über das Jahr 2024', fontsize=14, pad=20)
plt.legend(loc='upper left', bbox_to_anchor=(0.02, 0.98))

# Zusätzliche Statistiken für den Akku
akku_min = combined_df['simu_akku_kwh'].min()
akku_max = combined_df['simu_akku_kwh'].max()
akku_mean = combined_df['simu_akku_kwh'].mean()
akku_std = combined_df['simu_akku_kwh'].std()

# Prüfe ob Minimum verletzt wurde
min_verletzungen = (combined_df['simu_akku_kwh'] < min_akku_kapazitat).sum()

# Hausverbrauch Statistiken
verbrauch_mean = combined_df['hausverbrauch_kwh'].mean()
verbrauch_max = combined_df['hausverbrauch_kwh'].max()
pv_mean = combined_df['pv_gesamt_kwh_erweitert'].mean()
pv_max = combined_df['pv_gesamt_kwh_erweitert'].max()

# Statistikbox
stats_text = f'''Akku Statistiken:
Min: {akku_min:.2f} kWh
Max: {akku_max:.2f} kWh
Mittel: {akku_mean:.2f} kWh
Std: {akku_std:.2f} kWh
Min-Verletzungen: {min_verletzungen}

Verbrauch/PV:
Verbrauch Ø: {verbrauch_mean:.2f} kWh/h
Verbrauch Max: {verbrauch_max:.2f} kWh/h
PV Ø: {pv_mean:.2f} kWh/h
PV Max: {pv_max:.2f} kWh/h'''

plt.text(0.75, 0.98, stats_text, transform=plt.gca().transAxes, verticalalignment='top', 
         bbox=dict(boxstyle='round', facecolor='white', alpha=0.9), fontsize=10)

plt.tight_layout()
plt.show()







# ------------------- SUMMARY-BERECHNUNG -------------------

# Gesamtverbrauch (Haus) in kWh über den Zeitraum
gesamt_verbrauch_kwh = combined_df['hausverbrauch_kwh'].sum()

# Gesamt-PV-Produktion
gesamt_pv_kwh = combined_df['pv_gesamt_kwh_erweitert'].sum()

# PV direkt genutzt (nicht eingespeist)
pv_direktnutzung_kwh = combined_df['hausverbrauch_kwh'].where(
    combined_df['pv_gesamt_kwh_erweitert'] >= combined_df['hausverbrauch_kwh'],
    combined_df['pv_gesamt_kwh_erweitert']
).sum()

# PV-Energie, die in den Akku geladen wurde
akku_ladungen_kwh = np.diff(simuAkku, prepend=simuAkku[0])
akku_energie_von_pv_kwh = akku_ladungen_kwh[akku_ladungen_kwh > 0].sum()

# PV-Energie, die aus dem Akku entnommen wurde
akku_entnahmen_kwh = -akku_ladungen_kwh[akku_ladungen_kwh < 0].sum()

# Gesamt-Netzbezug (laut Sensor)
netzbezug_kwh = combined_df['sensor.netznutzung_kwh'].sum()

# Autarkiegrad (wie viel % des Verbrauchs durch PV + Akku gedeckt wurde)
verbrauch_deckt_durch_pv_und_akku = pv_direktnutzung_kwh + akku_entnahmen_kwh
autarkiegrad = (verbrauch_deckt_durch_pv_und_akku / gesamt_verbrauch_kwh) * 100

# Einfache Einsparung: was du nicht aus dem Netz holen musstest
eingespart_kwh = verbrauch_deckt_durch_pv_und_akku

# ------------------- AKKU-ERSARNIS IN CHF -------------------

strompreis_bezug_rp = 22.5  # Rappen pro kWh für Bezug
einspeiseverg_rp = 7.5*0.8      # Rappen pro kWh für Einspeisung

# Was der Akku an Netzstrom spart (in Rappen)
ersparnis_durch_vermeidung_netbezug_rp = akku_entnahmen_kwh * strompreis_bezug_rp

# Was man "verliert", weil man weniger einspeist (in Rappen)
verlust_durch_verhinderte_einspeisung_rp = akku_energie_von_pv_kwh * einspeiseverg_rp

# Nettoersparnis durch Akku (in Rappen)
netto_ersparnis_akku_rp = ersparnis_durch_vermeidung_netbezug_rp - verlust_durch_verhinderte_einspeisung_rp

# Umrechnung in CHF
netto_ersparnis_akku_chf = netto_ersparnis_akku_rp / 100

# ------------------- AUSGABE -------------------

print("\n=== JAHRESSTATISTIKEN 2024 ===")
yearly_sums = combined_df.sum()
print(f"PV Gesamt erweitert: {yearly_sums['pv_gesamt_kwh_erweitert']:.1f} kWh")
print(f"Hausverbrauch: {yearly_sums['hausverbrauch_kwh']:.1f} kWh")
print(f"PV Überschuss: {yearly_sums['pv_uebrig_kwh']:.1f} kWh")
print(f"Netznutzung: {yearly_sums['sensor.netznutzung_kwh']:.1f} kWh")
print(f"Netzeinspeisung: {yearly_sums['sensor.netzeinspeisung_kwh']:.1f} kWh")

autarkie_grad = (1 - yearly_sums['sensor.netznutzung_kwh'] / yearly_sums['hausverbrauch_kwh']) * 100
eigenverbrauchsquote = (yearly_sums['pv_gesamt_kwh_erweitert'] - yearly_sums['sensor.netzeinspeisung_kwh']) / yearly_sums['pv_gesamt_kwh_erweitert'] * 100

print(f"\nAutarkie-Grad (ohne Akku): {autarkie_grad:.1f}%")
print(f"Eigenverbrauchsquote (ohne Akku): {eigenverbrauchsquote:.1f}%")

print("\n=== ENERGIE-SUMMARY MIT AKKU ===")
print(f"Gesamtverbrauch:         {gesamt_verbrauch_kwh:.2f} kWh")
print(f"PV-Gesamterzeugung:      {gesamt_pv_kwh:.2f} kWh")
print(f"Direkt genutzte PV:      {pv_direktnutzung_kwh:.2f} kWh")
print(f"Energie in Akku geladen: {akku_energie_von_pv_kwh:.2f} kWh")
print(f"Aus dem Akku entnommen:  {akku_entnahmen_kwh:.2f} kWh")
print(f"Netzbezug:               {netzbezug_kwh:.2f} kWh")
print(f"Gesparte Energie (PV+Akku): {eingespart_kwh:.2f} kWh")
print(f"Autarkiegrad (mit Akku): {autarkiegrad:.1f}%")

print("\n=== FINANZIELLE ERSPARNIS (AKKU) ===")
print(f"Netzstrom durch Akku vermieden:   {akku_entnahmen_kwh:.2f} kWh → {ersparnis_durch_vermeidung_netbezug_rp:.2f} Rp")
print(f"Verhinderte Einspeisung:          {akku_energie_von_pv_kwh:.2f} kWh → {verlust_durch_verhinderte_einspeisung_rp:.2f} Rp")
print(f"💰 Nettoersparnis durch Akku:     {netto_ersparnis_akku_chf:.2f} CHF")
print("=====================================")