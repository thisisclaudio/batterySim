import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# Liste der zu extrahierenden Sensoren
sensors = [
    'sensor.netznutzung_kwh',
    'sensor.netzeinspeisung_kwh',
    'sensor.sma_st_80_total_yield',
    'sensor.sn_3012091531_pv_gen_meter'
]

# Lade die CSV-Datei
df = pd.read_csv('data/energyData24Hourly.csv')

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

# Gib die Datenreihen für weitere Verwendung aus
print("Verfügbare Datenreihen (stündliche Differenzen):")
for sensor, series in data_dict.items():
    print(f"\n{sensor}:")
    print(series.head())  # Zeige die ersten paar Einträge jeder Datenreihe

# Erstelle den Plot für die stündlichen Differenzen
plt.figure(figsize=(14, 8))
for sensor, series in data_dict.items():
    plt.plot(series.index, series, label=sensor, linewidth=1)

plt.xlabel('Zeit')
plt.ylabel('Stündliche Differenz (kWh)')
plt.title('Stündliche Differenzen der Energiewerte für 2024')
plt.legend()
plt.grid(True)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()