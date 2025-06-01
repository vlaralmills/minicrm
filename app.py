from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import calendar
import re
import json
import requests
from io import BytesIO
import os
import logging

# Ρύθμιση logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

class GoogleDriveDataLoader:
    def __init__(self):
        # Environment variables
        self.file_id = os.getenv('GOOGLE_DRIVE_FILE_ID')
        self.api_key = os.getenv('GOOGLE_DRIVE_API_KEY')
        
        # Cache settings
        self.df = None
        self.last_loaded = None
        self.cache_duration = 3600  # 1 ώρα
        
        if not self.file_id:
            logging.warning("GOOGLE_DRIVE_FILE_ID not set. Using fallback method.")
        
    def download_excel_from_drive(self):
        """Κατεβάζει το Excel από Google Drive"""
        try:
            if self.api_key and self.file_id:
                # Μέθοδος με API Key
                url = f"https://www.googleapis.com/drive/v3/files/{self.file_id}"
                params = {'alt': 'media', 'key': self.api_key}
                
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                
            else:
                # Fallback: Direct download (το αρχείο πρέπει να είναι public)
                url = f"https://drive.google.com/uc?id={self.file_id}&export=download"
                response = requests.get(url, timeout=30)
                response.raise_for_status()
            
            # Φόρτωση Excel από memory
            excel_data = BytesIO(response.content)
            df = pd.read_excel(excel_data)
            
            logging.info(f"Successfully loaded {len(df)} rows from Google Drive")
            return df
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error downloading from Google Drive: {e}")
            raise Exception(f"Σφάλμα δικτύου: {e}")
        except Exception as e:
            logging.error(f"Error processing Excel from Google Drive: {e}")
            raise Exception(f"Σφάλμα επεξεργασίας αρχείου: {e}")
    
    def get_dataframe(self, force_refresh=False):
        """Επιστρέφει το DataFrame με caching"""
        import time
        
        current_time = time.time()
        
        # Έλεγχος αν χρειάζεται refresh
        should_refresh = (
            force_refresh or 
            self.df is None or 
            self.last_loaded is None or 
            (current_time - self.last_loaded) > self.cache_duration
        )
        
        if should_refresh:
            logging.info("Refreshing data from Google Drive...")
            try:
                self.df = self.download_excel_from_drive()
                self.last_loaded = current_time
                
                # Καθαρισμός δεδομένων
                self._clean_dataframe()
                
            except Exception as e:
                logging.error(f"Failed to refresh data: {e}")
                if self.df is None:
                    # Αν δεν έχουμε καθόλου δεδομένα, δημιούργησε κενό DataFrame
                    self.df = pd.DataFrame()
                # Αλλιώς χρησιμοποίησε τα cached δεδομένα
        
        return self.df
    
    def _clean_dataframe(self):
        """Καθαρισμός και προετοιμασία των δεδομένων"""
        if self.df is not None and not self.df.empty:
            # Καθαρισμός στηλών
            self.df.columns = self.df.columns.str.strip()
            
            # Μετατροπή τιμών σε αριθμούς
            self.df['Μικτό ποσό'] = pd.to_numeric(self.df['Μικτό ποσό'], errors='coerce')
            self.df['Τρέχον Υπόλοιπο'] = pd.to_numeric(
                self.df['Τρέχον Υπόλοιπο'].astype(str).str.replace(',', '.', regex=False),
                errors='coerce'
            )
            self.df['ημερες βαση συμφωνιας'] = pd.to_numeric(self.df['ημερες βαση συμφωνιας'], errors='coerce')
            self.df['Μεταχ'] = pd.to_numeric(self.df['Μεταχ'], errors='coerce')

# Δημιουργία global instance
data_loader = GoogleDriveDataLoader()

def clean_for_json(obj):
    """Καθαρισμός δεδομένων για JSON serialization"""
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, (float, np.floating)):
        if np.isnan(obj) or np.isinf(obj):
            return 0
        return float(obj)
    elif isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj

def parse_month_data(month_str):
    """Εξάγει μήνα και έτος από διάφορα formats"""
    if pd.isna(month_str):
        return None, None
        
    month_str = str(month_str).strip()
    
    # Pattern για "(MM)" στην αρχή
    match = re.match(r'^\((\d{1,2})\)', month_str)
    if match:
        month = int(match.group(1))
        return month, None
    
    # Άλλα patterns
    for pattern in [r'^(\d{1,2})_(\d{4})$', r'^(\d{1,2})/(\d{4})$', r'^(\d{1,2})-(\d{4})$']:
        match = re.match(pattern, month_str)
        if match:
            return int(match.group(1)), int(match.group(2))
    
    return None, None

def calculate_credit_days(client_df, balance):
    """Υπολογισμός ημερών πίστωσης"""
    if not isinstance(balance, (int, float)) or balance <= 0:
        return '-'
    
    working_df = client_df.copy()
    
    # Parsing μηνών
    month_year_data = []
    for idx, row in working_df.iterrows():
        month_str = row.get('Μήνας', '')
        year_from_col = row.get('Ετος', None)
        month, year = parse_month_data(month_str)
        
        if year is None and pd.notna(year_from_col):
            year = int(year_from_col)
        
        if year is None:
            year = datetime.now().year
            
        month_year_data.append({
            'month': month,
            'year': year,
            'amount': row.get('Μικτό ποσό', 0)
        })
    
    # Φιλτράρισμα έγκυρων δεδομένων
    valid_data = [
        d for d in month_year_data 
        if d['month'] is not None and d['year'] is not None and pd.notna(d['amount']) and d['amount'] > 0
    ]
    
    if len(valid_data) == 0:
        return '-'
    
    # Συνάθροιση ανά μήνα/έτος
    month_totals = {}
    for d in valid_data:
        key = (d['year'], d['month'])
        if key not in month_totals:
            month_totals[key] = 0
        month_totals[key] += d['amount']
    
    # Ταξινόμηση από το πιο πρόσφατο στο παλιότερο
    sorted_months = sorted(month_totals.items(), key=lambda x: (x[0][0], x[0][1]), reverse=True)
    
    cumulative = 0
    total_days = 0
    
    for (year, month), amount in sorted_months:
        try:
            days_in_month = calendar.monthrange(year, month)[1]
            daily_rate = amount / days_in_month
            
            if cumulative + amount >= balance:
                remaining_needed = balance - cumulative
                partial_days = remaining_needed / daily_rate if daily_rate > 0 else 0
                total_days += partial_days
                break
            else:
                cumulative += amount
                total_days += days_in_month
                
        except (ValueError, TypeError):
            continue
    
    return round(total_days) if total_days > 0 else '-'

def calculate_collectible_amount(balance, credit_days, agreement_days):
    """Υπολογισμός εισπρακτέου ποσού"""
    try:
        balance = float(balance) if pd.notna(balance) else 0
        credit_days = float(credit_days) if pd.notna(credit_days) else 0
        agreement_days = float(agreement_days) if pd.notna(agreement_days) else 0
    except (ValueError, TypeError):
        return '-'
    
    if balance <= 0 or credit_days <= 0 or agreement_days < 0:
        return '-'
    
    if credit_days <= agreement_days:
        return 0
    
    excess_days = credit_days - agreement_days
    collectible_ratio = excess_days / credit_days
    collectible_amount = balance * collectible_ratio
    
    return round(collectible_amount, 2)

@app.route('/')
def index():
    try:
        df = data_loader.get_dataframe()
        client_names = sorted(df['Ονομα 1'].dropna().unique().tolist()) if not df.empty else []
        return render_template('index.html', clients=client_names)
    except Exception as e:
        logging.error(f"Error in index route: {e}")
        return render_template('index.html', clients=[])

@app.route('/clients-list')
def get_clients_list():
    try:
        df = data_loader.get_dataframe()
        client_names = sorted(df['Ονομα 1'].dropna().unique().tolist()) if not df.empty else []
        return jsonify(client_names)
    except Exception as e:
        logging.error(f"Error getting clients list: {e}")
        return jsonify([])

@app.route('/client')
def get_client_data():
    try:
        df = data_loader.get_dataframe()
        if df.empty:
            return jsonify({'error': 'Δεν είναι διαθέσιμα δεδομένα. Ελέγξτε τη σύνδεση.'}), 500
            
        name = request.args.get('name')
        if not name:
            return jsonify({'error': 'Missing client name'}), 400

        client_df = df[df['Ονομα 1'] == name]
        if client_df.empty:
            return jsonify({'error': 'Client not found'}), 404

        # Τρέχον υπόλοιπο
        balance_series = client_df['Τρέχον Υπόλοιπο'].dropna()
        balance = balance_series.iloc[0] if not balance_series.empty else '-'
        
        # Ημέρες βάση συμφωνίας
        agreement_days_series = client_df['ημερες βαση συμφωνιας'].dropna()
        agreement_days = agreement_days_series.iloc[0] if not agreement_days_series.empty else '-'
        
        # Μεταχ
        metax_series = client_df['Μεταχ'].dropna()
        metax = metax_series.iloc[0] if not metax_series.empty else 0

        # Υπολογισμός ημερών πίστωσης
        credit_days = calculate_credit_days(client_df, balance)
        
        # Υπολογισμός εισπρακτέου ποσού
        collectible_amount = '-'
        if (balance != '-' and credit_days != '-' and agreement_days != '-'):
            collectible_amount = calculate_collectible_amount(balance, credit_days, agreement_days)

        # Υλικά με περιγραφή και τιμές
        materials = []
        unique_materials = client_df['Υλικό'].dropna().unique()
        for mat in unique_materials:
            mat_df = client_df[client_df['Υλικό'] == mat]
            
            price = 0
            if 'τιμή ανα συσκευασία' in mat_df.columns:
                recent_prices = mat_df['τιμή ανα συσκευασία'].dropna()
                price = recent_prices.iloc[-1] if not recent_prices.empty else 0
                
            description = ''
            if 'Περιγραφή Υλικού' in mat_df.columns:
                descriptions = mat_df['Περιγραφή Υλικού'].dropna()
                description = descriptions.iloc[0] if not descriptions.empty else ''
                
            materials.append({
                'Υλικό': mat,
                'Περιγραφή': description,
                'Τιμή ανά συσκευασία': round(float(price), 2) if pd.notna(price) else 0
            })

        # Μήνες
        available_months = sorted(df['Μήνας'].dropna().unique().tolist())

        # Μηνιαίος τζίρος
        monthly_turnover = (
            client_df.groupby('Μήνας')['Μικτό ποσό']
            .sum()
            .reindex(available_months, fill_value=0)
            .round(2)
            .to_dict()
        )

        # Κατανόμη υλικών
        material_usage = {}
        if 'Τιμολ.ποσ.' in client_df.columns:
            material_usage = (
                client_df.groupby(['Υλικό', 'Μήνας'])['Τιμολ.ποσ.']
                .sum()
                .unstack(fill_value=0)
                .reindex(columns=available_months, fill_value=0)
                .round(2)
                .to_dict(orient='index')
            )

        # Συνδυασμός υλικού με τιμή και ποσά
        detailed_materials = []
        for mat in materials:
            usage = material_usage.get(mat['Υλικό'], {})
            mat_entry = {
                'Υλικό': mat['Υλικό'],
                'Περιγραφή': mat['Περιγραφή'],
                'Τιμή ανά συσκευασία': mat['Τιμή ανά συσκευασία'],
            }
            for month in available_months:
                mat_entry[str(month)] = usage.get(month, 0)
            detailed_materials.append(mat_entry)

        # Απάντηση
        response_data = {
            'Ονομα 1': name,
            'Πληρωτής': client_df['Πληρωτής'].iloc[0] if 'Πληρωτής' in client_df.columns else '-',
            'Μεταχ': metax,
            'Τρέχον Υπόλοιπο': balance,
            'Ημέρες Πίστωσης': credit_days,
            'Ημέρες Βάση Συμφωνίας': agreement_days,
            'Εισπρακτέο Ποσό': collectible_amount,
            'Μήνες': available_months,
            'Μηνιαίος Τζίρος': monthly_turnover,
            'Υλικά': detailed_materials
        }

        return jsonify(clean_for_json(response_data))
        
    except Exception as e:
        logging.error(f"Error getting client data: {e}")
        return jsonify({'error': f'Σφάλμα επεξεργασίας δεδομένων: {str(e)}'}), 500

@app.route('/refresh-data')
def refresh_data():
    """Manual refresh των δεδομένων"""
    try:
        df = data_loader.get_dataframe(force_refresh=True)
        return jsonify({
            'status': 'success', 
            'message': f'Δεδομένα ανανεώθηκαν επιτυχώς. Φορτώθηκαν {len(df)} γραμμές.'
        })
    except Exception as e:
        logging.error(f"Error refreshing data: {e}")
        return jsonify({'error': f'Αποτυχία ανανέωσης δεδομένων: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Health check για το Render"""
    try:
        df = data_loader.get_dataframe()
        return jsonify({
            'status': 'healthy',
            'data_loaded': not df.empty,
            'rows': len(df) if not df.empty else 0,
            'cache_age': data_loader.last_loaded
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)