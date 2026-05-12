"""Reentrenamiento con features estructurales/locacionales únicamente."""
import pandas as pd
import numpy as np
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from xgboost import XGBRegressor

df = pd.read_csv('data/raw/SmartHome_Valuator_Dataset_CLEAN.csv', skiprows=1)

FEATURES_NUM = [
    'Área (m²)', 'Habitaciones', 'Baños', 'Antigüedad (años)',
    'Estrato', 'Latitud', 'Longitud',
    'Hurto Res./100k hab', 'Índice Seguridad (0-10)',
]
FEATURES_CAT = ['Tipo Inmueble', 'Localidad', 'UPZ']
TARGET = 'PRECIO MERCADO (COP) ★'

def preprocess(df_in):
    df_p = df_in.copy()
    df_p['Parqueadero'] = df_p['Parqueadero'].map({'Sí': 1, 'No': 0}).fillna(0).astype(int)
    df_p['Depósito']    = df_p['Depósito'].map({'Sí': 1, 'No': 0}).fillna(0).astype(int)
    for col in FEATURES_NUM:
        df_p[col] = pd.to_numeric(df_p[col], errors='coerce')
        df_p[col] = df_p[col].fillna(df_p[col].median())
    encoders = {}
    for col in FEATURES_CAT:
        le = LabelEncoder()
        df_p[col] = le.fit_transform(df_p[col].astype(str))
        encoders[col] = le
    df_p = df_p.dropna(subset=[TARGET])
    df_p = df_p[df_p[TARGET] > 0]
    feature_cols = FEATURES_NUM + FEATURES_CAT + ['Parqueadero', 'Depósito']
    return df_p[feature_cols], df_p[TARGET], encoders

df_venta    = df[df['Tipo Operación'] == 'Venta'].copy()
df_arriendo = df[df['Tipo Operación'] == 'Arriendo'].copy()

X_v, y_v, enc_v = preprocess(df_venta)
X_a, y_a, enc_a = preprocess(df_arriendo)
print(f'Features ({X_v.shape[1]}): {list(X_v.columns)}')

def split(X, y):
    Xtr, Xtmp, ytr, ytmp = train_test_split(X, y, test_size=0.30, random_state=42)
    Xval, Xte, yval, yte = train_test_split(Xtmp, ytmp, test_size=0.50, random_state=42)
    return Xtr, Xval, Xte, ytr, yval, yte

def train(Xtr, ytr, Xval, yval, Xte, yte, label):
    print(f'\n[{label}] y_train: mean={ytr.mean():,.0f}  min={ytr.min():,.0f}  max={ytr.max():,.0f}')
    m = XGBRegressor(
        n_estimators=500, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        eval_metric='rmse', early_stopping_rounds=20,
    )
    m.fit(Xtr, ytr, eval_set=[(Xval, yval)], verbose=False)
    yp = m.predict(Xte)
    r2   = r2_score(yte, yp)
    rmse = np.sqrt(mean_squared_error(yte, yp))
    mae  = mean_absolute_error(yte, yp)
    print(f'  R²={r2:.4f}  RMSE={rmse:,.0f} COP  MAE={mae:,.0f} COP  best_iter={m.best_iteration}')

    # Importancia de features
    fi = pd.Series(m.feature_importances_, index=Xtr.columns).sort_values(ascending=False)
    print('  Top features:')
    for fname, fval in fi.head(6).items():
        print(f'    {fval:.3f}  {fname}')

    # Predicciones por estrato
    tmp = Xte.copy()
    tmp['y_pred'] = yp
    g = tmp.groupby('Estrato')['y_pred'].agg(['mean', 'min', 'max']).map(lambda x: f'{x:,.0f}')
    print('  Predicción por estrato (test set):')
    print(g.to_string())
    return m

Xtr_v, Xval_v, Xte_v, ytr_v, yval_v, yte_v = split(X_v, y_v)
Xtr_a, Xval_a, Xte_a, ytr_a, yval_a, yte_a = split(X_a, y_a)

m_v = train(Xtr_v, ytr_v, Xval_v, yval_v, Xte_v, yte_v, 'XGBoost Venta')
m_a = train(Xtr_a, ytr_a, Xval_a, yval_a, Xte_a, yte_a, 'XGBoost Arriendo')

MODELS_DIR = 'services/ml/models'
rename = {'Tipo Inmueble': 'tipo_inmueble', 'Localidad': 'localidad', 'UPZ': 'upz'}
joblib.dump(m_v,  os.path.join(MODELS_DIR, 'xgboost_venta.pkl'))
joblib.dump(m_a,  os.path.join(MODELS_DIR, 'xgboost_arriendo.pkl'))
joblib.dump({rename.get(k, k): v for k, v in enc_v.items()}, os.path.join(MODELS_DIR, 'encoders_venta.pkl'))
joblib.dump({rename.get(k, k): v for k, v in enc_a.items()}, os.path.join(MODELS_DIR, 'encoders_arriendo.pkl'))
print('\nArtefactos guardados en services/ml/models/')
