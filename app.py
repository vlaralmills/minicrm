from flask import Flask, render_template_string, request, jsonify
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

# HTML Template ως string (για να αποφύγουμε το templates folder issue)
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="UTF-8">
  <title>Αναφορά Πελάτη</title>
  <link rel="icon" href="data:,">
  <style>
    body { 
      font-family: sans-serif; 
      padding: 2rem; 
      background-color: #f5f5f5;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      background-color: white;
      padding: 2rem;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    select, button { 
      font-size: 16px; 
      padding: 0.5rem; 
      margin: 0.5rem;
    }
    button {
      background-color: #007bff;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      margin: 0 5px;
    }
    button:hover {
      background-color: #0056b3;
    }
    #voiceBtn {
      background-color: #28a745;
    }
    #voiceBtn:hover {
      background-color: #1e7e34;
    }
    #voiceBtn.listening {
      background-color: #dc3545;
      animation: pulse 1s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.05); }
      100% { transform: scale(1); }
    }
    .client-info {
      background-color: #f8f9fa;
      padding: 1.5rem;
      border-radius: 6px;
      margin: 1rem 0;
      border-left: 4px solid #007bff;
    }
    .info-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1rem;
      margin-bottom: 1rem;
    }
    .info-item {
      background-color: white;
      padding: 1rem;
      border-radius: 4px;
      border: 1px solid #dee2e6;
    }
    .info-label {
      font-weight: bold;
      color: #495057;
      display: block;
      margin-bottom: 0.5rem;
    }
    .info-value {
      font-size: 1.1em;
      color: #212529;
    }
    .highlight {
      background-color: #fff3cd;
      border-color: #ffeaa7;
    }
    .collectible {
      background-color: #d1ecf1;
      border-color: #bee5eb;
    }
    .collectible .info-value {
      font-weight: bold;
      color: #0c5460;
    }
    .metax-item {
      background-color: #e7f3ff;
      border-color: #b3d9ff;
    }
    .metax-item .info-value {
      font-weight: bold;
      color: #0056b3;
    }
    table { 
      border-collapse: collapse; 
      margin-top: 1rem; 
      width: 100%;
      background-color: white;
    }
    th, td { 
      border: 1px solid #dee2e6; 
      padding: 8px; 
      text-align: center; 
    }
    th { 
      background-color: #e9ecef;
      font-weight: bold;
      color: #495057;
    }
    .total-row {
      background-color: #f8f9fa;
      font-weight: bold;
    }
    h2 {
      color: #343a40;
      text-align: center;
      margin-bottom: 2rem;
    }
    h3 {
      color: #495057;
      border-bottom: 2px solid #007bff;
      padding-bottom: 0.5rem;
    }
    h4 {
      color: #6c757d;
      margin-top: 2rem;
    }
    .error-message {
      background-color: #f8d7da;
      color: #721c24;
      padding: 1rem;
      border-radius: 4px;
      margin: 1rem 0;
      border-left: 4px solid #dc3545;
    }
    .status-message {
      background-color: #d4edda;
      color: #155724;
      padding: 1rem;
      border-radius: 4px;
      margin: 1rem 0;
      border-left: 4px solid #28a745;
    }
  </style>
</head>
<body>
  <div class="container">
    <h2>📊 Αναφορά Πελάτη</h2>
    
    {% if error_message %}
    <div class="error-message">
      ⚠️ {{ error_message }}
    </div>
    {% endif %}
    
    {% if status_message %}
    <div class="status-message">
      ✅ {{ status_message }}
    </div>
    {% endif %}
    
    <div style="text-align: center; margin-bottom: 2rem;">
      <select id="clientSelect" style="min-width: 300px;">
        <option value="">-- Επιλέξτε Πελάτη --</option>
        {% for name in clients %}
        <option value="{{ name }}">{{ name }}</option>
        {% endfor %}
      </select>
      <button onclick="fetchClient()">🔍 Αναζήτηση</button>
      <button id="voiceBtn" onclick="startVoiceSearch()">🎤 Φωνητική Αναζήτηση</button>
      <div id="voiceStatus" style="margin-top: 1rem; font-style: italic; color: #6c757d;"></div>
    </div>

    <div id="result"></div>
  </div>

  <script>
    let recognition;
    let isListening = false;
    let clientsList = [];

    // Φόρτωση λίστας πελατών
    async function loadClientsList() {
      try {
        const response = await fetch('/clients-list');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        clientsList = await response.json();
      } catch (error) {
        console.error('Error loading clients list:', error);
        const selectElement = document.getElementById('clientSelect');
        clientsList = [];
        for (let i = 0; i < selectElement.options.length; i++) {
          const option = selectElement.options[i];
          if (option.value && option.value.trim() !== '') {
            clientsList.push(option.value);
          }
        }
      }
    }

    // Αρχικοποίηση Speech Recognition
    function initSpeechRecognition() {
      if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.lang = 'el-GR';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 5;

        recognition.onstart = function() {
          document.getElementById('voiceStatus').innerText = '🎤 Ακούω... Πείτε το όνομα του πελάτη';
          document.getElementById('voiceBtn').classList.add('listening');
          document.getElementById('voiceBtn').innerText = '🔴 Ακρόαση...';
          isListening = true;
        };

        recognition.onresult = function(event) {
          const spokenText = event.results[0][0].transcript.toLowerCase();
          document.getElementById('voiceStatus').innerText = `📝 Άκουσα: "${spokenText}"`;
          
          const matchedClient = findBestMatch(spokenText);
          if (matchedClient) {
            document.getElementById('clientSelect').value = matchedClient;
            document.getElementById('voiceStatus').innerText = `✅ Βρέθηκε: ${matchedClient}`;
            setTimeout(() => fetchClient(), 1000);
          } else {
            document.getElementById('voiceStatus').innerText = `❌ Δεν βρέθηκε πελάτης που να ταιριάζει με: "${spokenText}"`;
          }
        };

        recognition.onerror = function(event) {
          let errorMsg = 'Σφάλμα αναγνώρισης φωνής';
          switch(event.error) {
            case 'network': errorMsg = '🌐 Πρόβλημα δικτύου'; break;
            case 'not-allowed': errorMsg = '🚫 Δεν επιτρέπεται η πρόσβαση στο μικρόφωνο'; break;
            case 'no-speech': errorMsg = '🔇 Δεν ανιχνεύτηκε ομιλία'; break;
            default: errorMsg = `❌ Σφάλμα: ${event.error}`;
          }
          document.getElementById('voiceStatus').innerText = errorMsg;
          resetVoiceButton();
        };

        recognition.onend = function() {
          resetVoiceButton();
        };

        return true;
      } else {
        document.getElementById('voiceStatus').innerText = '❌ Ο περιηγητής δεν υποστηρίζει φωνητική αναγνώριση';
        document.getElementById('voiceBtn').disabled = true;
        return false;
      }
    }

    function resetVoiceButton() {
      document.getElementById('voiceBtn').classList.remove('listening');
      document.getElementById('voiceBtn').innerText = '🎤 Φωνητική Αναζήτηση';
      isListening = false;
    }

    function findBestMatch(spokenText) {
      let bestMatch = null;
      let bestScore = 0;
      for (const client of clientsList) {
        const score = calculateSimilarity(spokenText, client.toLowerCase());
        if (score > bestScore && score > 0.3) {
          bestScore = score;
          bestMatch = client;
        }
      }
      return bestMatch;
    }

    function calculateSimilarity(text1, text2) {
      text1 = normalizeGreekText(text1);
      text2 = normalizeGreekText(text2);

      if (text2.includes(text1) || text1.includes(text2)) {
        return 0.8;
      }

      const words1 = text1.split(/\\s+/);
      const words2 = text2.split(/\\s+/);
      
      let matchingWords = 0;
      for (const word1 of words1) {
        if (word1.length > 2) {
          for (const word2 of words2) {
            if (word2.includes(word1) || word1.includes(word2)) {
              matchingWords++;
              break;
            }
          }
        }
      }
      return matchingWords / Math.max(words1.length, words2.length);
    }

    function normalizeGreekText(text) {
      return text.toLowerCase()
        .replace(/ά/g, 'α').replace(/έ/g, 'ε').replace(/ή/g, 'η')
        .replace(/ί/g, 'ι').replace(/ό/g, 'ο').replace(/ύ/g, 'υ')
        .replace(/ώ/g, 'ω').replace(/ΐ/g, 'ι').replace(/ΰ/g, 'υ')
        .replace(/[^\\u0370-\\u03FF\\u1F00-\\u1FFF\\s]/g, '');
    }

    function startVoiceSearch() {
      if (clientsList.length === 0) {
        document.getElementById('voiceStatus').innerText = '⏳ Φόρτωση λίστας πελατών...';
        return;
      }

      if (!recognition) {
        if (!initSpeechRecognition()) {
          return;
        }
      }

      if (isListening) {
        recognition.stop();
        return;
      }

      try {
        recognition.start();
      } catch (error) {
        document.getElementById('voiceStatus').innerText = '❌ Σφάλμα έναρξης αναγνώρισης φωνής';
      }
    }

    window.onload = async function() {
      await loadClientsList();
      initSpeechRecognition();
    };

    function fetchClient() {
      const name = document.getElementById('clientSelect').value;
      if (!name) return alert('Επιλέξτε πελάτη');

      fetch(`/client?name=${encodeURIComponent(name)}`)
        .then(res => res.json())
        .then(data => {
          if (data.error) return alert(data.error);

          const months = data['Μήνες'] || [];
          const turnover = data['Μηνιαίος Τζίρος'] || {};
          const materials = data['Υλικά'] || [];

          const collectibleAmount = data['Εισπρακτέο Ποσό'];
          const collectibleClass = (collectibleAmount > 0) ? 'collectible' : '';

          const metaxValue = data['Μεταχ'];
          const metaxClass = (metaxValue !== 0 && metaxValue !== '-') ? 'metax-item' : '';

          let html = `
            <div class="client-info">
              <h3>📋 Στοιχεία Πελάτη</h3>
              <div class="info-grid">
                <div class="info-item">
                  <span class="info-label">👤 Όνομα:</span>
                  <span class="info-value">${data['Ονομα 1']}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">💳 Πληρωτής:</span>
                  <span class="info-value">${data['Πληρωτής']}</span>
                </div>
                <div class="info-item ${metaxClass}">
                  <span class="info-label">📊 Μεταχ:</span>
                  <span class="info-value">${typeof metaxValue === 'number' ? metaxValue.toFixed(2) + '€' : metaxValue}</span>
                </div>
                <div class="info-item highlight">
                  <span class="info-label">💰 Τρέχον Υπόλοιπο:</span>
                  <span class="info-value">${typeof data['Τρέχον Υπόλοιπο'] === 'number' ? data['Τρέχον Υπόλοιπο'].toFixed(2) + '€' : data['Τρέχον Υπόλοιπο']}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">📅 Ημέρες Πίστωσης:</span>
                  <span class="info-value">${data['Ημέρες Πίστωσης']}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">📋 Ημέρες Βάση Συμφωνίας:</span>
                  <span class="info-value">${data['Ημέρες Βάση Συμφωνίας']}</span>
                </div>
                <div class="info-item ${collectibleClass}">
                  <span class="info-label">🎯 Εισπρακτέο Ποσό:</span>
                  <span class="info-value">${typeof collectibleAmount === 'number' ? collectibleAmount.toFixed(2) + '€' : collectibleAmount}</span>
                </div>
              </div>
            </div>

            <h4>📈 Τζίρος & Χρήση Υλικών</h4>
            <table>
              <tr>
                <th>Υλικό</th>
                <th>Τιμή/συσκ.(€)</th>
                ${months.map(m => `<th>${m}</th>`).join('')}
              </tr>
              <tr class="total-row">
                <td><strong>💼 Σύνολο Τζίρου</strong></td>
                <td>–</td>
                ${months.map(m => `<td><strong>${(turnover[m] || 0).toFixed(2)}€</strong></td>`).join('')}
              </tr>`;

          for (const mat of materials) {
            html += `
              <tr>
                <td style="text-align: left;">${mat['Υλικό']}</td>
                <td>${mat['Τιμή ανά συσκευασία']?.toFixed(2) || '-'}€</td>
                ${months.map(m => `<td>${(mat[m] || 0).toFixed(2)}</td>`).join('')}
              </tr>`;
          }

          html += '</table>';
          document.getElementById('result').innerHTML = html;

          setTimeout(() => {
            document.getElementById('voiceStatus').innerText = '';
          }, 3000);
        })
        .catch(err => {
          console.error('Error:', err);
          alert('Σφάλμα κατά την ανάκτηση δεδομένων');
        });
    }
  </script>
</body>
</html>'''

class GoogleDriveDataLoader:
    def __init__(self):
        # Environment variables - χρησιμοποίησε μόνο το File ID χωρίς επιπλέον παραμέτρους
        self.file_id = os.getenv('GOOGLE_DRIVE_FILE_ID', '').split('/')[0].split('?')[0]  # Καθαρισμός
        self.api_key = os.getenv('GOOGLE_DRIVE_API_KEY')
        
        self.df = None
        self.last_loaded = None
        self.cache_duration = 3600  # 1 ώρα
        
        logging.info(f"Initialized with File ID: {self.file_id}")
        
    def download_excel_from_drive(self):
        """Κατεβάζει το Excel από Google Drive με fallback methods"""
        if not self.file_id:
            raise Exception("Δεν έχει οριστεί Google Drive File ID")
            
        methods = [
            self._download_with_api,
            self._download_direct_public,
            self._download_alternative_public
        ]
        
        for i, method in enumerate(methods, 1):
            try:
                logging.info(f"Trying download method {i}...")
                df = method()
                logging.info(f"Successfully downloaded with method {i}: {len(df)} rows")
                return df
            except Exception as e:
                logging.warning(f"Method {i} failed: {e}")
                if i == len(methods):
                    raise Exception(f"Όλες οι μέθοδοι κατεβάσματος απέτυχαν. Τελευταίο σφάλμα: {e}")
                continue
    
    def _download_with_api(self):
        """Μέθοδος με API Key"""
        if not self.api_key:
            raise Exception("No API key provided")
            
        url = f"https://www.googleapis.com/drive/v3/files/{self.file_id}"
        params = {'alt': 'media', 'key': self.api_key}
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        excel_data = BytesIO(response.content)
        return pd.read_excel(excel_data)
    
    def _download_direct_public(self):
        """Direct download για public αρχεία"""
        url = f"https://drive.google.com/uc?id={self.file_id}&export=download"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        excel_data = BytesIO(response.content)
        return pd.read_excel(excel_data)
    
    def _download_alternative_public(self):
        """Εναλλακτική μέθοδος για public αρχεία"""
        url = f"https://docs.google.com/spreadsheets/d/{self.file_id}/export?format=xlsx"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        excel_data = BytesIO(response.content)
        return pd.read_excel(excel_data)
    
    def get_dataframe(self, force_refresh=False):
        """Επιστρέφει το DataFrame με caching"""
        import time
        
        current_time = time.time()
        
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
                self._clean_dataframe()
                
            except Exception as e:
                logging.error(f"Failed to refresh data: {e}")
                if self.df is None:
                    self.df = pd.DataFrame()
        
        return self.df
    
    def _clean_dataframe(self):
        """Καθαρισμός και προετοιμασία των δεδομένων"""
        if self.df is not None and not self.df.empty:
            self.df.columns = self.df.columns.str.strip()
            
            # Μετατροπή τιμών σε αριθμούς
            numeric_cols = ['Μικτό ποσό', 'ημερες βαση συμφωνιας', 'Μεταχ']
            for col in numeric_cols:
                if col in self.df.columns:
                    self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
            
            # Ειδική μεταχείριση για Τρέχον Υπόλοιπο
            if 'Τρέχον Υπόλοιπο' in self.df.columns:
                self.df['Τρέχον Υπόλοιπο'] = pd.to_numeric(
                    self.df['Τρέχον Υπόλοιπο'].astype(str).str.replace(',', '.', regex=False),
                    errors='coerce'
                )

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
    
    match = re.match(r'^\((\d{1,2})\)', month_str)
    if match:
        month = int(match.group(1))
        return month, None
    
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
    
    valid_data = [
        d for d in month_year_data 
        if d['month'] is not None and d['year'] is not None and pd.notna(d['amount']) and d['amount'] > 0
    ]
    
    if len(valid_data) == 0:
        return '-'
    
    month_totals = {}
    for d in valid_data:
        key = (d['year'], d['month'])
        if key not in month_totals:
            month_totals[key] = 0
        month_totals[key] += d['amount']
    
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
        
        # Έλεγχος κατάστασης δεδομένων
        error_message = None
        status_message = None
        
        if df.empty:
            error_message = "Δεν ήταν δυνατή η φόρτωση δεδομένων από το Google Drive. Ελέγξτε το File ID και τις ρυθμίσεις."
        elif len(client_names) > 0:
            status_message = f"Φορτώθηκαν επιτυχώς {len(df)} εγγραφές με {len(client_names)} πελάτες."
        
        return render_template_string(HTML_TEMPLATE, 
                                    clients=client_names,
                                    error_message=error_message,
                                    status_message=status_message)
                                    
    except Exception as e:
        logging.error(f"Error in index route: {e}")
        error_message = f"Σφάλμα εφαρμογής: {str(e)}"
        return render_template_string(HTML_TEMPLATE, 
                                    clients=[],
                                    error_message=error_message,
                                    status_message=None)

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
            return jsonify({'error': 'Δεν είναι διαθέσιμα δεδομένα. Ελέγξτε τη σύνδεση με το Google Drive.'}), 500
            
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
            'message': f'Δεδομένα ανανεώθηκαν επιτυχώς. Φορτώθηκαν {len(df)} γραμμές.',
            'rows': len(df),
            'file_id': data_loader.file_id
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
            'cache_age': data_loader.last_loaded,
            'file_id': data_loader.file_id,
            'has_api_key': bool(data_loader.api_key)
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy', 
            'error': str(e),
            'file_id': data_loader.file_id,
            'has_api_key': bool(data_loader.api_key)
        }), 500

@app.route('/debug')
def debug_info():
    """Debug endpoint για troubleshooting"""
    try:
        return jsonify({
            'environment_vars': {
                'GOOGLE_DRIVE_FILE_ID': os.getenv('GOOGLE_DRIVE_FILE_ID'),
                'has_api_key': bool(os.getenv('GOOGLE_DRIVE_API_KEY')),
                'flask_env': os.getenv('FLASK_ENV', 'development')
            },
            'file_id_cleaned': data_loader.file_id,
            'cache_info': {
                'has_data': data_loader.df is not None,
                'data_rows': len(data_loader.df) if data_loader.df is not None else 0,
                'last_loaded': data_loader.last_loaded
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)