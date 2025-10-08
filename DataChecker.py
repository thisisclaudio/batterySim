import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from datetime import datetime, timedelta

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
        # Runde Zeitstempel auf die nächste volle Stunde
        df_sensor_indexed.index = df_sensor_indexed.index.round('h')
        # Entferne Duplikate nach dem Runden (falls vorhanden)
        df_sensor_indexed = df_sensor_indexed.groupby(df_sensor_indexed.index).first()
        # Aktualisiere nur die Stunden, für die Daten vorhanden sind
        common_index = df_sensor_indexed.index.intersection(df_complete.index)
        df_complete.loc[common_index, 'hourly_diff'] = df_sensor_indexed.loc[common_index, 'hourly_diff']
    else:
        # Für Netz-Sensoren: normale Zuordnung (diese haben meist alle Stunden)
        # Runde auch hier die Zeitstempel für Konsistenz
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
combined_df['sensor.sn_3012091531_pv_gen_meter_erweitert'] = combined_df['sensor.sn_3012091531_pv_gen_meter'] * 7

# Berechne den PV Gesamt mit der erweiterten West Anlage
combined_df['pv_gesamt_kwh_erweitert'] = (combined_df['sensor.sma_st_80_total_yield'] + 
                                         combined_df['sensor.sn_3012091531_pv_gen_meter_erweitert'])

# Berechne den PV Überschuss
combined_df['pv_uebrig_kwh'] = combined_df['pv_gesamt_kwh_erweitert'] - combined_df['hausverbrauch_kwh']




# Konvertiere Index zu timezone-naive
combined_df.index = combined_df.index.tz_localize(None)

# Plotte das ganze Jahr 2024
plt.figure(figsize=(20, 12))

# Subplot 1: Monatliche Summen
plt.subplot(2, 2, 1)
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
plt.subplot(2, 2, 2)
daily_avg = combined_df.resample('D').sum().resample('M').mean()
plt.plot(months, daily_avg['pv_gesamt_kwh_erweitert'], marker='o', label='PV Gesamt erweitert (kWh/Tag)', linewidth=2)
plt.plot(months, daily_avg['hausverbrauch_kwh'], marker='s', label='Hausverbrauch (kWh/Tag)', linewidth=2)
plt.plot(months, daily_avg['pv_uebrig_kwh'], marker='^', label='PV Überschuss (kWh/Tag)', linewidth=2)
plt.xlabel('Monat')
plt.ylabel('kWh/Tag')
plt.title('Durchschnittliche tägliche Energiewerte pro Monat')
plt.legend()
plt.grid(True, alpha=0.3)
plt.xticks(range(1, 13))

# Subplot 3: Wöchentliche Mittelwerte über das Jahr
plt.subplot(2, 2, 3)
weekly_avg = combined_df.resample('W').sum()
plt.plot(weekly_avg.index, weekly_avg['pv_gesamt_kwh_erweitert'], label='PV Gesamt erweitert (kWh/Woche)', linewidth=2)
plt.plot(weekly_avg.index, weekly_avg['hausverbrauch_kwh'], label='Hausverbrauch (kWh/Woche)', linewidth=2)
plt.plot(weekly_avg.index, weekly_avg['pv_uebrig_kwh'], label='PV Überschuss (kWh/Woche)', linewidth=2)
plt.xlabel('Datum')
plt.ylabel('kWh/Woche')
plt.title('Wöchentliche Energiesummen 2024')
plt.legend()
plt.grid(True, alpha=0.3)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(rotation=45)

# Subplot 4: Tägliche Summen über das Jahr (kompakt)
plt.subplot(2, 2, 4)
daily_sums = combined_df.resample('D').sum()
plt.plot(daily_sums.index, daily_sums['pv_gesamt_kwh_erweitert'], alpha=0.7, label='PV Gesamt erweitert (kWh/Tag)')
plt.plot(daily_sums.index, daily_sums['hausverbrauch_kwh'], alpha=0.7, label='Hausverbrauch (kWh/Tag)')
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

plt.tight_layout()
plt.show()

# Zusätzlich: Jahresstatistiken ausgeben
print("\n=== JAHRESSTATISTIKEN 2024 ===")
yearly_sums = combined_df.sum()
print(f"PV Gesamt erweitert: {yearly_sums['pv_gesamt_kwh_erweitert']:.1f} kWh")
print(f"Hausverbrauch: {yearly_sums['hausverbrauch_kwh']:.1f} kWh")
print(f"PV Überschuss: {yearly_sums['pv_uebrig_kwh']:.1f} kWh")
print(f"Netznutzung: {yearly_sums['sensor.netznutzung_kwh']:.1f} kWh")
print(f"Netzeinspeisung: {yearly_sums['sensor.netzeinspeisung_kwh']:.1f} kWh")

autarkie_grad = (1 - yearly_sums['sensor.netznutzung_kwh'] / yearly_sums['hausverbrauch_kwh']) * 100
eigenverbrauchsquote = (yearly_sums['pv_gesamt_kwh_erweitert'] - yearly_sums['sensor.netzeinspeisung_kwh']) / yearly_sums['pv_gesamt_kwh_erweitert'] * 100

print(f"\nAutarkie-Grad: {autarkie_grad:.1f}%")
print(f"Eigenverbrauchsquote: {eigenverbrauchsquote:.1f}%")

