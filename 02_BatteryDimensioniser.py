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

# ------------------- MULTI-AKKU-SIMULATION -------------------

akku_groessen = [5, 10, 15, 20, 25, 35]  # kWh
akku_resultate = {}

# Strompreise (in Rappen)
strompreis_bezug_rp = 22.5
einspeiseverg_rp = 7.5

zeitintervall = 1.0  # Stundenbasis
akku_wirkungsgrad_laden = 0.95
akku_wirkungsgrad_entladen = 0.95
max_lade_leistung = 3.0
max_entlade_leistung = 3.0
start_soc = 0.5

# Hauptschleife über alle Akkugrößen
for kapazitaet in akku_groessen:
    min_kapazitaet = kapazitaet * 0.1
    akku_stand = kapazitaet * start_soc
    simu_akku = np.zeros(len(combined_df))
    
    for i in range(len(combined_df)):
        pv_ueberschuss = combined_df['pv_uebrig_kwh'].iloc[i]
        
        if pv_ueberschuss > 0:
            verfuegbarer_platz = kapazitaet - akku_stand
            ladeenergie_brutto = min(pv_ueberschuss, max_lade_leistung * zeitintervall)
            ladeenergie_netto = min(ladeenergie_brutto * akku_wirkungsgrad_laden, verfuegbarer_platz)
            akku_stand += ladeenergie_netto
        elif pv_ueberschuss < 0:
            benoetigte_energie = abs(pv_ueberschuss)
            verfuegbare_energie = max(0, akku_stand - min_kapazitaet)
            max_entladeenergie = min(max_entlade_leistung * zeitintervall, verfuegbare_energie)
            entladeenergie_netto = min(benoetigte_energie, max_entladeenergie)
            akku_stand -= entladeenergie_netto
        
        akku_stand = max(min_kapazitaet, min(akku_stand, kapazitaet))
        simu_akku[i] = akku_stand
    
    # Differenz zur Berechnung Lade-/Entladeenergie
    akku_diff = np.diff(simu_akku, prepend=simu_akku[0])
    geladen = akku_diff[akku_diff > 0].sum()
    entladen = -akku_diff[akku_diff < 0].sum()

    # Wirtschaftlichkeit
    ersparnis_rp = entladen * strompreis_bezug_rp
    verlust_rp = geladen * einspeiseverg_rp
    netto_rp = ersparnis_rp - verlust_rp
    netto_chf = netto_rp / 100

    # Monatliche Ersparnis (CHFs pro Monat)
    df_copy = combined_df.copy()
    df_copy['akku_diff'] = akku_diff
    df_copy['akku_entladen'] = df_copy['akku_diff'].apply(lambda x: -x if x < 0 else 0)
    df_copy['akku_geladen'] = df_copy['akku_diff'].apply(lambda x: x if x > 0 else 0)
    df_copy['ersparnis_chf'] = (df_copy['akku_entladen'] * strompreis_bezug_rp - df_copy['akku_geladen'] * einspeiseverg_rp) / 100

    monatliche_ersparnis = df_copy['ersparnis_chf'].resample('M').sum()

    # Speichern der Resultate
    akku_resultate[kapazitaet] = {
        'simu_akku': simu_akku,
        'geladen_kwh': geladen,
        'entladen_kwh': entladen,
        'netto_chf': netto_chf,
        'monatliche_ersparnis': monatliche_ersparnis
    }

# ------------------- VISUALISIERUNG -------------------

# 1️⃣ Jahresersparnis pro Akku
kapazitaeten = list(akku_resultate.keys())
jahres_ersparnis = [akku_resultate[k]['netto_chf'] for k in kapazitaeten]

plt.figure(figsize=(10, 5))
plt.bar(kapazitaeten, jahres_ersparnis, color='skyblue', edgecolor='black')
plt.title('Jährliche Nettoersparnis durch Akkus unterschiedlicher Größe (2024)')
plt.xlabel('Akkukapazität [kWh]')
plt.ylabel('Ersparnis [CHF/Jahr]')
plt.grid(axis='y', alpha=0.3)
for i, v in enumerate(jahres_ersparnis):
    plt.text(kapazitaeten[i], v + 0.5, f"{v:.1f} CHF", ha='center', va='bottom')
plt.tight_layout()
plt.show()

# 2️⃣ Monatliche Ersparnisverläufe
plt.figure(figsize=(14, 7))
for kapazitaet, result in akku_resultate.items():
    plt.plot(result['monatliche_ersparnis'].index, result['monatliche_ersparnis'].values, label=f"{kapazitaet} kWh")

plt.title('Monatliche Nettoersparnis pro Akkugröße (2024)')
plt.xlabel('Monat')
plt.ylabel('Ersparnis [CHF/Monat]')
plt.legend(title="Akkukapazität")
plt.grid(True, alpha=0.3)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b'))
plt.tight_layout()
plt.show()

# ------------------- AUSGABE DER ERGEBNISSE -------------------

print("\n=== JAHRESERGEBNIS PRO AKKU ===")
for k in akku_groessen:
    r = akku_resultate[k]
    print(f"{k:>3} kWh Akku:  Ersparnis = {r['netto_chf']:.2f} CHF   "
          f"(geladen: {r['geladen_kwh']:.1f} kWh, entladen: {r['entladen_kwh']:.1f} kWh)")


#Visualisiere die Gesamtersparnis abhäniggig von der Akkugröße
plt.figure(figsize=(10, 5))
for k in akku_groessen:
    r = akku_resultate[k]
    plt.bar(k, r['netto_chf'], color='skyblue', edgecolor='black')
plt.title('Jährliche Nettoersparnis in Abhängigkeit von der Akkugröße (2024)')
plt.xlabel('Akkukapazität [kWh]')
plt.ylabel('Ersparnis [CHF/Jahr]')
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.show()
