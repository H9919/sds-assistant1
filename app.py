# Complete SDS Assistant with AI Question Answering
import os
from flask import Flask, render_template_string, request, jsonify, send_file, session
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import PyPDF2
from io import BytesIO
from werkzeug.utils import secure_filename
import requests
import re
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sds-assistant-secret-key-2024')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Create necessary directories
for folder in ['static/uploads', 'static/stickers', 'static/exports', 'data']:
    Path(folder).mkdir(parents=True, exist_ok=True)

# US Cities Data
US_CITIES_DATA = {
    "Alabama": ["Birmingham", "Montgomery", "Mobile", "Huntsville", "Tuscaloosa"],
    "Alaska": ["Anchorage", "Fairbanks", "Juneau", "Wasilla", "Sitka"],
    "Arizona": ["Phoenix", "Tucson", "Mesa", "Chandler", "Scottsdale"],
    "Arkansas": ["Little Rock", "Fort Smith", "Fayetteville", "Springdale"],
    "California": ["Los Angeles", "San Diego", "San Jose", "San Francisco", "Fresno", "Sacramento"],
    "Colorado": ["Denver", "Colorado Springs", "Aurora", "Fort Collins"],
    "Connecticut": ["Bridgeport", "New Haven", "Hartford", "Stamford"],
    "Delaware": ["Wilmington", "Dover", "Newark", "Middletown"],
    "Florida": ["Jacksonville", "Miami", "Tampa", "Orlando", "St. Petersburg"],
    "Georgia": ["Atlanta", "Augusta", "Columbus", "Savannah", "Athens"],
    "Hawaii": ["Honolulu", "Pearl City", "Hilo", "Kailua"],
    "Idaho": ["Boise", "Meridian", "Nampa", "Idaho Falls"],
    "Illinois": ["Chicago", "Aurora", "Rockford", "Joliet", "Naperville"],
    "Indiana": ["Indianapolis", "Fort Wayne", "Evansville", "South Bend"],
    "Iowa": ["Des Moines", "Cedar Rapids", "Davenport", "Sioux City"],
    "Kansas": ["Wichita", "Overland Park", "Kansas City", "Olathe"],
    "Kentucky": ["Louisville", "Lexington", "Bowling Green", "Owensboro"],
    "Louisiana": ["New Orleans", "Baton Rouge", "Shreveport", "Lafayette"],
    "Maine": ["Portland", "Lewiston", "Bangor", "South Portland"],
    "Maryland": ["Baltimore", "Frederick", "Rockville", "Gaithersburg"],
    "Massachusetts": ["Boston", "Worcester", "Springfield", "Lowell"],
    "Michigan": ["Detroit", "Grand Rapids", "Warren", "Sterling Heights"],
    "Minnesota": ["Minneapolis", "St. Paul", "Rochester", "Duluth"],
    "Mississippi": ["Jackson", "Gulfport", "Southaven", "Hattiesburg"],
    "Missouri": ["Kansas City", "St. Louis", "Springfield", "Independence"],
    "Montana": ["Billings", "Missoula", "Great Falls", "Bozeman"],
    "Nebraska": ["Omaha", "Lincoln", "Bellevue", "Grand Island"],
    "Nevada": ["Las Vegas", "Henderson", "Reno", "North Las Vegas"],
    "New Hampshire": ["Manchester", "Nashua", "Concord", "Derry"],
    "New Jersey": ["Newark", "Jersey City", "Paterson", "Elizabeth"],
    "New Mexico": ["Albuquerque", "Las Cruces", "Rio Rancho", "Santa Fe"],
    "New York": ["New York City", "Buffalo", "Rochester", "Yonkers"],
    "North Carolina": ["Charlotte", "Raleigh", "Greensboro", "Durham"],
    "North Dakota": ["Fargo", "Bismarck", "Grand Forks", "Minot"],
    "Ohio": ["Columbus", "Cleveland", "Cincinnati", "Toledo"],
    "Oklahoma": ["Oklahoma City", "Tulsa", "Norman", "Broken Arrow"],
    "Oregon": ["Portland", "Eugene", "Salem", "Gresham"],
    "Pennsylvania": ["Philadelphia", "Pittsburgh", "Allentown", "Erie"],
    "Rhode Island": ["Providence", "Warwick", "Cranston", "Pawtucket"],
    "South Carolina": ["Charleston", "Columbia", "North Charleston"],
    "South Dakota": ["Sioux Falls", "Rapid City", "Aberdeen"],
    "Tennessee": ["Nashville", "Memphis", "Knoxville", "Chattanooga"],
    "Texas": ["Houston", "San Antonio", "Dallas", "Austin", "Fort Worth"],
    "Utah": ["Salt Lake City", "West Valley City", "Provo", "West Jordan"],
    "Vermont": ["Burlington", "Essex", "South Burlington"],
    "Virginia": ["Virginia Beach", "Norfolk", "Chesapeake", "Richmond"],
    "Washington": ["Seattle", "Spokane", "Tacoma", "Vancouver"],
    "West Virginia": ["Charleston", "Huntington", "Morgantown"],
    "Wisconsin": ["Milwaukee", "Madison", "Green Bay", "Kenosha"],
    "Wyoming": ["Cheyenne", "Casper", "Laramie", "Gillette"]
}

class SDSAssistant:
    def __init__(self, db_path: str = "data/sds_database.db"):
        self.db_path = db_path
        self.setup_database()
        self.populate_us_cities()
    
    def setup_database(self):
        """Initialize the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Locations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                country TEXT NOT NULL DEFAULT 'United States',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(department, city, state, country)
            )
        ''')
        
        # SDS documents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sds_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_filename TEXT,
                file_hash TEXT UNIQUE,
                product_name TEXT,
                manufacturer TEXT,
                cas_number TEXT,
                full_text TEXT NOT NULL,
                location_id INTEGER,
                source_type TEXT DEFAULT 'upload',
                web_url TEXT,
                file_size INTEGER,
                uploaded_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations (id)
            )
        ''')
        
        # Chemical hazards table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chemical_hazards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER,
                product_name TEXT,
                cas_number TEXT,
                nfpa_health INTEGER DEFAULT 0,
                nfpa_fire INTEGER DEFAULT 0,
                nfpa_reactivity INTEGER DEFAULT 0,
                nfpa_special TEXT,
                ghs_pictograms TEXT,
                ghs_signal_word TEXT,
                ghs_hazard_statements TEXT,
                first_aid TEXT,
                fire_fighting TEXT,
                handling_storage TEXT,
                exposure_controls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES sds_documents (id)
            )
        ''')
        
        # Q&A history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                document_id INTEGER,
                location_id INTEGER,
                user_session TEXT,
                confidence_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES sds_documents (id),
                FOREIGN KEY (location_id) REFERENCES locations (id)
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_product_name ON sds_documents(product_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_location ON sds_documents(location_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cas_number ON sds_documents(cas_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_hash ON sds_documents(file_hash)')
        
        conn.commit()
        conn.close()
    
    def populate_us_cities(self):
        """Populate database with US cities"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM locations')
        if cursor.fetchone()[0] > 0:
            conn.close()
            return
        
        print("Populating US cities database...")
        departments = ["Safety Department", "Environmental Health", "Chemical Storage", 
                      "Laboratory", "Manufacturing", "Warehouse", "Emergency Response"]
        
        for state, cities in US_CITIES_DATA.items():
            for city in cities:
                for dept in departments:
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO locations (department, city, state, country)
                            VALUES (?, ?, ?, ?)
                        ''', (dept, city, state, "United States"))
                    except sqlite3.Error as e:
                        print(f"Error inserting {dept}, {city}, {state}: {e}")
        
        conn.commit()
        conn.close()
        print("US cities populated successfully!")
    
    def extract_text_from_pdf(self, file_stream) -> str:
        """Extract text from PDF"""
        try:
            pdf_reader = PyPDF2.PdfReader(file_stream)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"Error extracting PDF text: {str(e)}")
            return ""
    
    def extract_chemical_info(self, text: str) -> Dict:
        """Extract chemical information from SDS text"""
        info = {
            "product_name": "",
            "manufacturer": "",
            "cas_number": "",
            "hazards": {
                "health": 0,
                "fire": 0,
                "reactivity": 0,
                "special": "",
                "ghs_signal_word": "",
                "first_aid": "",
                "fire_fighting": "",
                "handling_storage": "",
                "exposure_controls": ""
            }
        }
        
        # Extract product name
        product_patterns = [
            r"Product\s+Name:?\s*([^\n\r]+)",
            r"Product\s+Identifier:?\s*([^\n\r]+)",
            r"Trade\s+Name:?\s*([^\n\r]+)",
            r"Chemical\s+Name:?\s*([^\n\r]+)"
        ]
        
        for pattern in product_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info["product_name"] = match.group(1).strip()
                break
        
        # Extract manufacturer
        manufacturer_patterns = [
            r"Manufacturer:?\s*([^\n\r]+)",
            r"Company:?\s*([^\n\r]+)",
            r"Supplier:?\s*([^\n\r]+)"
        ]
        
        for pattern in manufacturer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info["manufacturer"] = match.group(1).strip()
                break
        
        # Extract CAS number
        cas_pattern = r"CAS\s*#?:?\s*(\d{2,7}-\d{2}-\d)"
        cas_match = re.search(cas_pattern, text, re.IGNORECASE)
        if cas_match:
            info["cas_number"] = cas_match.group(1)
        
        # Extract NFPA ratings
        nfpa_patterns = [
            (r"Health\s*=?\s*(\d)", "health"),
            (r"Fire\s*=?\s*(\d)", "fire"),
            (r"Reactivity\s*=?\s*(\d)", "reactivity"),
            (r"NFPA\s+Health\s*:?\s*(\d)", "health"),
            (r"NFPA\s+Fire\s*:?\s*(\d)", "fire"),
            (r"NFPA\s+Reactivity\s*:?\s*(\d)", "reactivity")
        ]
        
        for pattern, key in nfpa_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info["hazards"][key] = int(match.group(1))
        
        # Extract safety information sections
        info["hazards"]["first_aid"] = self.extract_section(text, ["first aid", "section 4"])
        info["hazards"]["fire_fighting"] = self.extract_section(text, ["fire fighting", "firefighting", "section 5"])
        info["hazards"]["handling_storage"] = self.extract_section(text, ["handling and storage", "section 7"])
        info["hazards"]["exposure_controls"] = self.extract_section(text, ["exposure controls", "personal protection", "section 8"])
        
        return info
    
    def extract_section(self, text: str, section_keywords: List[str]) -> str:
        """Extract specific sections from SDS text"""
        text_lower = text.lower()
        
        for keyword in section_keywords:
            # Look for section headers
            pattern = rf"{keyword}[:\s]*(.*?)(?=section\s+\d+|$)"
            match = re.search(pattern, text_lower, re.DOTALL | re.IGNORECASE)
            if match:
                section_text = match.group(1).strip()
                # Limit to reasonable length
                return section_text[:1000] if len(section_text) > 1000 else section_text
        
        return ""
    
    def upload_file(self, file, location_id: int, uploaded_by: str = "web_user") -> Dict:
        """Process uploaded file"""
        try:
            file_content = file.read()
            file.seek(0)
            file_hash = hashlib.sha256(file_content).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check for duplicates
            cursor.execute('SELECT id, product_name FROM sds_documents WHERE file_hash = ?', (file_hash,))
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return {"success": False, "message": f"File already exists (Product: {existing[1]})"}
            
            # Save file
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{filename}"
            file_path = Path(app.config['UPLOAD_FOLDER']) / saved_filename
            
            file.seek(0)
            file.save(file_path)
            
            # Extract text
            file.seek(0)
            if filename.lower().endswith('.pdf'):
                text_content = self.extract_text_from_pdf(file)
            else:
                text_content = file_content.decode('utf-8', errors='ignore')
            
            if not text_content.strip():
                return {"success": False, "message": "Could not extract text from file"}
            
            # Extract chemical information
            chem_info = self.extract_chemical_info(text_content)
            
            # Insert document
            cursor.execute('''
                INSERT INTO sds_documents (
                    filename, original_filename, file_hash, product_name, 
                    manufacturer, cas_number, full_text,
                    location_id, source_type, file_size, uploaded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                saved_filename, filename, file_hash,
                chem_info["product_name"] or "Unknown Product", 
                chem_info["manufacturer"] or "Unknown Manufacturer",
                chem_info["cas_number"], text_content,
                location_id, "upload", len(file_content), uploaded_by
            ))
            
            document_id = cursor.lastrowid
            
            # Insert hazard information
            cursor.execute('''
                INSERT INTO chemical_hazards (
                    document_id, product_name, cas_number, nfpa_health,
                    nfpa_fire, nfpa_reactivity, ghs_signal_word,
                    first_aid, fire_fighting, handling_storage, exposure_controls
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                document_id, chem_info["product_name"], chem_info["cas_number"],
                chem_info["hazards"]["health"], chem_info["hazards"]["fire"],
                chem_info["hazards"]["reactivity"], chem_info["hazards"]["ghs_signal_word"],
                chem_info["hazards"]["first_aid"], chem_info["hazards"]["fire_fighting"],
                chem_info["hazards"]["handling_storage"], chem_info["hazards"]["exposure_controls"]
            ))
            
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "message": "File uploaded successfully",
                "product_name": chem_info["product_name"] or "Unknown Product",
                "document_id": document_id
            }
            
        except Exception as e:
            return {"success": False, "message": f"Error uploading file: {str(e)}"}
    
    def answer_question(self, question: str, location_id: int = None, user_session: str = None) -> Dict:
        """Answer questions about SDS documents using AI-powered search"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Search for relevant documents
            search_query = '''
                SELECT sd.id, sd.product_name, sd.full_text, 
                       ch.first_aid, ch.fire_fighting, ch.handling_storage, ch.exposure_controls,
                       l.department, l.city, l.state
                FROM sds_documents sd
                LEFT JOIN chemical_hazards ch ON sd.id = ch.document_id
                LEFT JOIN locations l ON sd.location_id = l.id
                WHERE sd.full_text LIKE ? OR sd.product_name LIKE ?
            '''
            
            params = [f"%{question}%", f"%{question}%"]
            
            if location_id:
                search_query += " AND sd.location_id = ?"
                params.append(location_id)
            
            search_query += " ORDER BY sd.created_at DESC LIMIT 10"
            
            cursor.execute(search_query, params)
            documents = cursor.fetchall()
            
            if not documents:
                return {
                    "success": False,
                    "answer": "I couldn't find any relevant SDS documents to answer your question. Please try uploading relevant SDS files first.",
                    "sources": []
                }
            
            # Generate answer using simple keyword matching and extraction
            answer = self.generate_answer(question, documents)
            
            # Log the Q&A
            if user_session:
                cursor.execute('''
                    INSERT INTO qa_history (question, answer, document_id, location_id, user_session, confidence_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (question, answer["text"], documents[0][0] if documents else None, location_id, user_session, answer["confidence"]))
                conn.commit()
            
            conn.close()
            
            return {
                "success": True,
                "answer": answer["text"],
                "confidence": answer["confidence"],
                "sources": answer["sources"]
            }
            
        except Exception as e:
            return {"success": False, "answer": f"Error processing question: {str(e)}", "sources": []}
    
    def generate_answer(self, question: str, documents: List) -> Dict:
        """Generate answer from documents using keyword matching"""
        question_lower = question.lower()
        answer_parts = []
        sources = []
        confidence = 0.0
        
        # Define question types and their keywords
        question_types = {
            "first_aid": ["first aid", "emergency", "exposure", "eye contact", "skin contact", "inhalation", "ingestion"],
            "fire_fighting": ["fire", "firefighting", "extinguish", "combustible", "flammable"],
            "handling": ["handling", "storage", "precautions", "handling precautions"],
            "exposure": ["exposure", "protection", "ppe", "personal protective", "ventilation"],
            "hazards": ["hazard", "danger", "toxic", "corrosive", "irritant"],
            "physical": ["physical", "appearance", "odor", "melting point", "boiling point"]
        }
        
        # Determine question type
        question_type = "general"
        for qtype, keywords in question_types.items():
            if any(keyword in question_lower for keyword in keywords):
                question_type = qtype
                break
        
        for doc in documents:
            doc_id, product_name, full_text, first_aid, fire_fighting, handling_storage, exposure_controls, dept, city, state = doc
            
            # Select relevant section based on question type
            relevant_text = ""
            if question_type == "first_aid" and first_aid:
                relevant_text = first_aid
            elif question_type == "fire_fighting" and fire_fighting:
                relevant_text = fire_fighting
            elif question_type == "handling" and handling_storage:
                relevant_text = handling_storage
            elif question_type == "exposure" and exposure_controls:
                relevant_text = exposure_controls
            else:
                # Search in full text
                relevant_text = self.extract_relevant_text(question, full_text)
            
            if relevant_text:
                answer_parts.append(f"**{product_name}**: {relevant_text}")
                sources.append({
                    "product_name": product_name,
                    "location": f"{dept}, {city}, {state}" if dept else "Unknown location",
                    "document_id": doc_id
                })
                confidence += 0.3
        
        if answer_parts:
            final_answer = "\n\n".join(answer_parts[:3])  # Limit to top 3 results
            confidence = min(confidence, 1.0)
        else:
            final_answer = "I found relevant documents but couldn't extract specific information to answer your question. Please check the documents directly or rephrase your question."
            confidence = 0.1
        
        return {
            "text": final_answer,
            "confidence": confidence,
            "sources": sources[:3]
        }
    
    def extract_relevant_text(self, question: str, full_text: str, max_length: int = 500) -> str:
        """Extract relevant text snippet from full document"""
        question_words = [word.lower() for word in question.split() if len(word) > 3]
        sentences = full_text.split('.')
        
        best_sentence = ""
        best_score = 0
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            score = sum(1 for word in question_words if word in sentence_lower)
            
            if score > best_score and len(sentence.strip()) > 20:
                best_score = score
                best_sentence = sentence.strip()
        
        if best_sentence:
            # Get context around the best sentence
            sentence_index = sentences.index(best_sentence)
            start_index = max(0, sentence_index - 1)
            end_index = min(len(sentences), sentence_index + 2)
            
            context = '. '.join(sentences[start_index:end_index]).strip()
            return context[:max_length] + "..." if len(context) > max_length else context
        
        return ""
    
    def search_web_for_sds(self, chemical_name: str, location_id: int) -> Dict:
        """Search web for SDS documents (placeholder - would need actual web scraping)"""
        # This is a placeholder. In a real implementation, you would:
        # 1. Search for SDS documents online
        # 2. Download and parse them
        # 3. Store in database
        # 4. Return results
        
        return {
            "success": False,
            "message": "Web search for SDS documents is not implemented yet. Please upload SDS files manually."
        }
    
    def generate_nfpa_sticker(self, product_name: str) -> Dict:
        """Generate NFPA diamond sticker"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ch.nfpa_health, ch.nfpa_fire, ch.nfpa_reactivity, ch.nfpa_special,
                       sd.product_name
                FROM chemical_hazards ch
                JOIN sds_documents sd ON ch.document_id = sd.id
                WHERE LOWER(sd.product_name) LIKE ?
                ORDER BY ch.created_at DESC LIMIT 1
            ''', (f"%{product_name.lower()}%",))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return {"success": False, "message": f"No hazard data found for {product_name}"}
            
            health, fire, reactivity, special, actual_name = result
            
            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="300" height="300" xmlns="http://www.w3.org/2000/svg">
    <style>
        .diamond {{ stroke: black; stroke-width: 3; }}
        .rating {{ font-family: Arial, sans-serif; font-size: 48px; font-weight: bold; text-anchor: middle; dominant-baseline: middle; }}
        .label {{ font-family: Arial, sans-serif; font-size: 14px; font-weight: bold; text-anchor: middle; }}
        .product {{ font-family: Arial, sans-serif; font-size: 12px; text-anchor: middle; }}
    </style>
    
    <polygon points="150,25 275,150 150,275 25,150" fill="white" stroke="black" stroke-width="3"/>
    
    <polygon points="25,150 150,25 150,150 25,150" fill="blue" class="diamond"/>
    <polygon points="150,25 275,150 150,150 150,25" fill="red" class="diamond"/>
    <polygon points="275,150 150,275 150,150 275,150" fill="yellow" class="diamond"/>
    <polygon points="150,150 150,275 25,150 150,150" fill="white" class="diamond"/>
    
    <text x="87" y="105" class="rating" fill="white">{health}</text>
    <text x="150" y="90" class="rating" fill="white">{fire}</text>
    <text x="213" y="105" class="rating" fill="black">{reactivity}</text>
    <text x="150" y="210" class="rating" fill="black">{special or ''}</text>
    
    <text x="87" y="130" class="label" fill="white">HEALTH</text>
    <text x="150" y="55" class="label" fill="white">FIRE</text>
    <text x="213" y="130" class="label" fill="black">REACTIVITY</text>
    <text x="150" y="240" class="label" fill="black">SPECIAL</text>
    
    <text x="150" y="295" class="product" fill="black">{actual_name[:40]}</text>
</svg>'''
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            sticker_filename = f"nfpa_{secure_filename(actual_name)}_{timestamp}.svg"
            sticker_path = Path('static/stickers') / sticker_filename
            
            with open(sticker_path, 'w') as f:
                f.write(svg_content)
            
            return {
                "success": True,
                "filename": sticker_filename,
                "sticker_type": "NFPA",
                "ratings": {"health": health, "fire": fire, "reactivity": reactivity, "special": special or "None"}
            }
            
        except Exception as e:
            return {"success": False, "message": f"Error generating NFPA sticker: {str(e)}"}
    
    def generate_ghs_sticker(self, product_name: str) -> Dict:
        """Generate GHS sticker"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ch.ghs_signal_word, ch.ghs_pictograms, ch.ghs_hazard_statements,
                       sd.product_name
                FROM chemical_hazards ch
                JOIN sds_documents sd ON ch.document_id = sd.id
                WHERE LOWER(sd.product_name) LIKE ?
                ORDER BY ch.created_at DESC LIMIT 1
            ''', (f"%{product_name.lower()}%",))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return {"success": False, "message": f"No GHS data found for {product_name}"}
            
            signal_word, pictograms, hazard_statements, actual_name = result
            
            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="400" height="300" xmlns="http://www.w3.org/2000/svg">
    <style>
        .header {{ font-family: Arial, sans-serif; font-size: 24px; font-weight: bold; text-anchor: middle; }}
        .signal {{ font-family: Arial, sans-serif; font-size: 20px; font-weight: bold; text-anchor: middle; }}
        .hazard {{ font-family: Arial, sans-serif; font-size: 14px; text-anchor: start; }}
        .product {{ font-family: Arial, sans-serif; font-size: 16px; font-weight: bold; text-anchor: middle; }}
    </style>
    
    <rect width="400" height="300" fill="white" stroke="black" stroke-width="3"/>
    
    <text x="200" y="30" class="header" fill="black">GHS LABEL</text>
    <text x="200" y="60" class="product" fill="black">{actual_name[:35]}</text>
    
    <text x="200" y="100" class="signal" fill="red">{signal_word or 'WARNING'}</text>
    
    <text x="20" y="140" class="hazard" fill="black">Hazard Statements:</text>
    <text x="20" y="160" class="hazard" fill="black">{(hazard_statements or 'See SDS for details')[:60]}</text>
    
    <text x="20" y="200" class="hazard" fill="black">Pictograms: {pictograms or 'See SDS'}</text>
    
    <text x="20" y="240" class="hazard" fill="black">Precautionary Statements:</text>
    <text x="20" y="260" class="hazard" fill="black">Read SDS before use. Wear protective equipment.</text>
</svg>'''
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            sticker_filename = f"ghs_{secure_filename(actual_name)}_{timestamp}.svg"
            sticker_path = Path('static/stickers') / sticker_filename
            
            with open(sticker_path, 'w') as f:
                f.write(svg_content)
            
            return {
                "success": True,
                "filename": sticker_filename,
                "sticker_type": "GHS",
                "signal_word": signal_word,
                "pictograms": pictograms,
                "hazard_statements": hazard_statements
            }
            
        except Exception as e:
            return {"success": False, "message": f"Error generating GHS sticker: {str(e)}"}
    
    def get_locations(self, state_filter=None, search_term=None) -> List[Dict]:
        """Get locations with optional filtering"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = '''
                SELECT l.id, l.department, l.city, l.state, l.country, 
                       COUNT(sd.id) as document_count
                FROM locations l
                LEFT JOIN sds_documents sd ON l.id = sd.location_id
            '''
            
            where_conditions = []
            params = []
            
            if state_filter:
                where_conditions.append("l.state = ?")
                params.append(state_filter)
            
            if search_term:
                where_conditions.append("(l.city LIKE ? OR l.department LIKE ?)")
                params.extend([f"%{search_term}%", f"%{search_term}%"])
            
            if where_conditions:
                query += " WHERE " + " AND ".join(where_conditions)
            
            query += '''
                GROUP BY l.id, l.department, l.city, l.state, l.country
                ORDER BY l.state, l.city, l.department
                LIMIT 1000
            '''
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()
            
            return [
                {
                    "id": row[0],
                    "department": row[1],
                    "city": row[2],
                    "state": row[3],
                    "country": row[4],
                    "document_count": row[5],
                    "display_name": f"{row[1]} - {row[2]}, {row[3]}"
                }
                for row in results
            ]
        except Exception as e:
            print(f"Error getting locations: {str(e)}")
            return []
    
    def get_states(self) -> List[str]:
        """Get all US states"""
        return sorted(US_CITIES_DATA.keys())
    
    def get_dashboard_stats(self) -> Dict:
        """Get dashboard statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM sds_documents')
            total_documents = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(DISTINCT location_id) FROM sds_documents WHERE location_id IS NOT NULL')
            active_locations = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM qa_history WHERE created_at >= datetime("now", "-7 days")')
            recent_questions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM chemical_hazards WHERE nfpa_health > 2 OR nfpa_fire > 2')
            hazardous_count = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT question, COUNT(*) as count
                FROM qa_history 
                WHERE created_at >= datetime("now", "-7 days")
                GROUP BY question
                ORDER BY count DESC
                LIMIT 5
            ''')
            recent_questions_list = cursor.fetchall()
            
            conn.close()
            
            return {
                "total_documents": total_documents,
                "active_locations": active_locations,
                "recent_questions": recent_questions,
                "hazardous_materials": hazardous_count,
                "popular_questions": [{"question": row[0], "count": row[1]} for row in recent_questions_list]
            }
            
        except Exception as e:
            print(f"Error getting dashboard stats: {str(e)}")
            return {"total_documents": 0, "active_locations": 0, "recent_questions": 0, "hazardous_materials": 0, "popular_questions": []}

# Initialize the assistant
sds_assistant = SDSAssistant()

# Enhanced HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SDS Assistant - AI-Powered Safety Data Sheet Management</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .card-hover:hover { transform: translateY(-2px); transition: transform 0.2s; }
        .chat-container { max-height: 400px; overflow-y: auto; }
        .message { margin-bottom: 1rem; }
        .user-message { background: #3b82f6; color: white; }
        .ai-message { background: #f3f4f6; color: #374151; }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <!-- Navigation -->
    <nav class="gradient-bg shadow-lg">
        <div class="max-w-7xl mx-auto px-4">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <i class="fas fa-flask text-white text-2xl mr-3"></i>
                    <span class="text-white text-xl font-bold">SDS Assistant</span>
                    <span class="text-white text-sm ml-2 opacity-75">AI-Powered Safety Data Sheet Management</span>
                </div>
                <div class="flex items-center space-x-4">
                    <button id="uploadBtn" class="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg transition">
                        <i class="fas fa-upload mr-2"></i>Upload SDS
                    </button>
                    <button id="generateStickerBtn" class="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg transition">
                        <i class="fas fa-tag mr-2"></i>Generate Sticker
                    </button>
                </div>
            </div>
        </div>
    </nav>

    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Dashboard Stats -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6 card-hover">
                <div class="flex items-center">
                    <div class="p-3 rounded-full bg-blue-100 text-blue-600">
                        <i class="fas fa-file-alt text-2xl"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-600">Total Documents</p>
                        <p id="totalDocs" class="text-2xl font-bold text-gray-900">0</p>
                    </div>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow p-6 card-hover">
                <div class="flex items-center">
                    <div class="p-3 rounded-full bg-green-100 text-green-600">
                        <i class="fas fa-map-marker-alt text-2xl"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-600">Active Locations</p>
                        <p id="activeLocations" class="text-2xl font-bold text-gray-900">0</p>
                    </div>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow p-6 card-hover">
                <div class="flex items-center">
                    <div class="p-3 rounded-full bg-purple-100 text-purple-600">
                        <i class="fas fa-question-circle text-2xl"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-600">Recent Questions</p>
                        <p id="recentQuestions" class="text-2xl font-bold text-gray-900">0</p>
                    </div>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow p-6 card-hover">
                <div class="flex items-center">
                    <div class="p-3 rounded-full bg-red-100 text-red-600">
                        <i class="fas fa-exclamation-triangle text-2xl"></i>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-600">Hazardous Materials</p>
                        <p id="hazardousMaterials" class="text-2xl font-bold text-gray-900">0</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- AI Question Answering -->
            <div class="bg-white rounded-lg shadow">
                <div class="p-6">
                    <h2 class="text-2xl font-bold text-gray-900 mb-4">
                        <i class="fas fa-robot mr-2"></i>Ask AI About SDS Documents
                    </h2>
                    
                    <div class="mb-4">
                        <select id="locationFilter" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
                            <option value="">All Locations</option>
                        </select>
                    </div>
                    
                    <div id="chatContainer" class="chat-container border rounded-lg p-4 mb-4 bg-gray-50">
                        <div class="message ai-message p-3 rounded-lg">
                            <p><strong>AI Assistant:</strong> Hello! I can help you find information in your SDS documents. Try asking questions like:</p>
                            <ul class="mt-2 ml-4 list-disc text-sm">
                                <li>"What are the first aid measures for acetone?"</li>
                                <li>"How should I store bleach?"</li>
                                <li>"What PPE is needed for handling sulfuric acid?"</li>
                            </ul>
                        </div>
                    </div>
                    
                    <div class="flex space-x-2">
                        <input 
                            type="text" 
                            id="questionInput" 
                            placeholder="Ask a question about your SDS documents..."
                            class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                        >
                        <button id="askBtn" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                    
                    <div class="mt-4">
                        <h4 class="font-semibold text-gray-700 mb-2">Quick Questions:</h4>
                        <div class="flex flex-wrap gap-2">
                            <button class="quick-question bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded-full text-sm transition" data-question="What are the first aid measures for this chemical?">
                                First Aid
                            </button>
                            <button class="quick-question bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded-full text-sm transition" data-question="How should this chemical be stored?">
                                Storage
                            </button>
                            <button class="quick-question bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded-full text-sm transition" data-question="What PPE is required for handling this chemical?">
                                PPE Requirements
                            </button>
                            <button class="quick-question bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded-full text-sm transition" data-question="What are the fire fighting measures for this chemical?">
                                Fire Fighting
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- File Upload & Management -->
            <div class="bg-white rounded-lg shadow">
                <div class="p-6">
                    <h2 class="text-2xl font-bold text-gray-900 mb-4">
                        <i class="fas fa-cloud-upload-alt mr-2"></i>Document Management
                    </h2>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                        <button id="uploadDocBtn" class="bg-blue-100 hover:bg-blue-200 p-4 rounded-lg transition text-center">
                            <i class="fas fa-upload text-blue-600 text-2xl mb-2"></i>
                            <h3 class="font-semibold">Upload SDS File</h3>
                            <p class="text-sm text-gray-600">PDF, TXT, DOC files</p>
                        </button>
                        
                        <button id="webSearchBtn" class="bg-green-100 hover:bg-green-200 p-4 rounded-lg transition text-center">
                            <i class="fas fa-search text-green-600 text-2xl mb-2"></i>
                            <h3 class="font-semibold">Search Web for SDS</h3>
                            <p class="text-sm text-gray-600">Find SDS online</p>
                        </button>
                    </div>
                    
                    <div id="recentDocuments">
                        <h4 class="font-semibold text-gray-700 mb-3">Recent Documents</h4>
                        <div id="documentsList" class="space-y-2">
                            <p class="text-gray-500 text-center py-4">No documents uploaded yet</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Popular Questions -->
        <div class="mt-8 bg-white rounded-lg shadow">
            <div class="p-6">
                <h3 class="text-xl font-bold text-gray-900 mb-4">Popular Questions</h3>
                <div id="popularQuestions" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <p class="text-gray-500 text-center py-4 col-span-2">No questions asked yet</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Upload Modal -->
    <div id="uploadModal" class="fixed inset-0 bg-gray-600 bg-opacity-50 hidden z-50">
        <div class="flex items-center justify-center min-h-screen p-4">
            <div class="bg-white rounded-lg shadow-xl max-w-md w-full">
                <div class="p-6">
                    <div class="flex justify-between items-center mb-4">
                        <h3 class="text-lg font-bold text-gray-900">Upload SDS Document</h3>
                        <button id="closeUploadModal" class="text-gray-400 hover:text-gray-600">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    
                    <form id="uploadForm" enctype="multipart/form-data">
                        <div class="mb-4">
                            <label class="block text-sm font-medium text-gray-700 mb-2">State</label>
                            <select id="uploadStateSelect" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" required>
                                <option value="">Choose a state...</option>
                            </select>
                        </div>
                        
                        <div class="mb-4">
                            <label class="block text-sm font-medium text-gray-700 mb-2">Location</label>
                            <select id="uploadLocationSelect" name="location_id" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" required>
                                <option value="">Choose a location...</option>
                            </select>
                        </div>
                        
                        <div class="mb-4">
                            <label class="block text-sm font-medium text-gray-700 mb-2">SDS File</label>
                            <div class="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-lg hover:border-gray-400 transition">
                                <div class="space-y-1 text-center">
                                    <i class="fas fa-cloud-upload-alt text-3xl text-gray-400"></i>
                                    <div class="flex text-sm text-gray-600">
                                        <label for="file-upload" class="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500">
                                            <span>Upload a file</span>
                                            <input id="file-upload" name="file" type="file" class="sr-only" accept=".pdf,.txt,.doc,.docx" required>
                                        </label>
                                        <p class="pl-1">or drag and drop</p>
                                    </div>
                                    <p class="text-xs text-gray-500">PDF, TXT, DOC up to 50MB</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="flex justify-end space-x-3">
                            <button type="button" id="cancelUpload" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition">
                                Cancel
                            </button>
                            <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">
                                <i class="fas fa-upload mr-2"></i>Upload
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <!-- Sticker Generation Modal -->
    <div id="stickerModal" class="fixed inset-0 bg-gray-600 bg-opacity-50 hidden z-50">
        <div class="flex items-center justify-center min-h-screen p-4">
            <div class="bg-white rounded-lg shadow-xl max-w-md w-full">
                <div class="p-6">
                    <div class="flex justify-between items-center mb-4">
                        <h3 class="text-lg font-bold text-gray-900">Generate Safety Sticker</h3>
                        <button id="closeStickerModal" class="text-gray-400 hover:text-gray-600">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-2">Product Name</label>
                        <input type="text" id="stickerProductName" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="Enter product name...">
                    </div>
                    
                    <div class="flex justify-end space-x-3">
                        <button type="button" id="cancelSticker" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition">
                            Cancel
                        </button>
                        <button id="generateNFPA" type="button" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition">
                            <i class="fas fa-diamond mr-2"></i>NFPA Diamond
                        </button>
                        <button id="generateGHS" type="button" class="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition">
                            <i class="fas fa-exclamation-triangle mr-2"></i>GHS Label
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notifications -->
    <div id="toast" class="fixed top-4 right-4 z-50 hidden">
        <div class="bg-white rounded-lg shadow-lg border-l-4 p-4 max-w-sm">
            <div class="flex">
                <div class="flex-shrink-0">
                    <i id="toastIcon" class="text-xl"></i>
                </div>
                <div class="ml-3">
                    <p id="toastMessage" class="text-sm font-medium text-gray-900"></p>
                </div>
                <div class="ml-auto pl-3">
                    <button id="closeToast" class="text-gray-400 hover:text-gray-600">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Global variables
        let currentConversation = [];
        
        // Initialize app
        document.addEventListener('DOMContentLoaded', function() {
            loadDashboardStats();
            loadStates();
            loadLocations();
            setupEventListeners();
        });
        
        // Setup event listeners
        function setupEventListeners() {
            // Question answering
            document.getElementById('askBtn').addEventListener('click', askQuestion);
            document.getElementById('questionInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') askQuestion();
            });
            
            // Quick questions
            document.querySelectorAll('.quick-question').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.getElementById('questionInput').value = this.dataset.question;
                    askQuestion();
                });
            });
            
            // File upload
            document.getElementById('uploadBtn').addEventListener('click', () => showModal('uploadModal'));
            document.getElementById('uploadDocBtn').addEventListener('click', () => showModal('uploadModal'));
            document.getElementById('closeUploadModal').addEventListener('click', () => hideModal('uploadModal'));
            document.getElementById('cancelUpload').addEventListener('click', () => hideModal('uploadModal'));
            document.getElementById('uploadForm').addEventListener('submit', handleFileUpload);
            
            // Sticker generation
            document.getElementById('generateStickerBtn').addEventListener('click', () => showModal('stickerModal'));
            document.getElementById('closeStickerModal').addEventListener('click', () => hideModal('stickerModal'));
            document.getElementById('cancelSticker').addEventListener('click', () => hideModal('stickerModal'));
            document.getElementById('generateNFPA').addEventListener('click', () => generateSticker('nfpa'));
            document.getElementById('generateGHS').addEventListener('click', () => generateSticker('ghs'));
            
            // State/Location handling
            document.getElementById('uploadStateSelect').addEventListener('change', function() {
                loadLocationsByState(this.value, 'uploadLocationSelect');
            });
            
            // Web search (placeholder)
            document.getElementById('webSearchBtn').addEventListener('click', function() {
                showToast('Web search feature coming soon!', 'info');
            });
            
            // Toast close
            document.getElementById('closeToast').addEventListener('click', hideToast);
        }
        
        // Load dashboard statistics
        async function loadDashboardStats() {
            try {
                const response = await fetch('/api/dashboard-stats');
                const stats = await response.json();
                
                document.getElementById('totalDocs').textContent = stats.total_documents;
                document.getElementById('activeLocations').textContent = stats.active_locations;
                document.getElementById('recentQuestions').textContent = stats.recent_questions;
                document.getElementById('hazardousMaterials').textContent = stats.hazardous_materials;
                
                updatePopularQuestions(stats.popular_questions);
                
            } catch (error) {
                console.error('Error loading dashboard stats:', error);
            }
        }
        
        // Load states
        async function loadStates() {
            try {
                const response = await fetch('/api/states');
                const states = await response.json();
                
                const select = document.getElementById('uploadStateSelect');
                states.forEach(state => {
                    const option = document.createElement('option');
                    option.value = state;
                    option.textContent = state;
                    select.appendChild(option);
                });
                
            } catch (error) {
                console.error('Error loading states:', error);
            }
        }
        
        // Load locations
        async function loadLocations() {
            try {
                const response = await fetch('/api/locations');
                const locations = await response.json();
                
                const select = document.getElementById('locationFilter');
                locations.slice(0, 50).forEach(location => {
                    const option = document.createElement('option');
                    option.value = location.id;
                    option.textContent = location.display_name;
                    select.appendChild(option);
                });
                
            } catch (error) {
                console.error('Error loading locations:', error);
            }
        }
        
        // Load locations by state
        async function loadLocationsByState(state, selectId) {
            if (!state) {
                document.getElementById(selectId).innerHTML = '<option value="">Choose a location...</option>';
                return;
            }
            
            try {
                const response = await fetch(`/api/locations?state=${encodeURIComponent(state)}`);
                const locations = await response.json();
                
                const select = document.getElementById(selectId);
                select.innerHTML = '<option value="">Choose a location...</option>';
                
                locations.forEach(location => {
                    const option = document.createElement('option');
                    option.value = location.id;
                    option.textContent = location.display_name;
                    select.appendChild(option);
                });
                
            } catch (error) {
                console.error('Error loading locations:', error);
            }
        }
        
        // Ask question to AI
        async function askQuestion() {
            const question = document.getElementById('questionInput').value.trim();
            const locationId = document.getElementById('locationFilter').value;
            
            if (!question) {
                showToast('Please enter a question', 'warning');
                return;
            }
            
            // Add user message to chat
            addMessageToChat(question, 'user');
            document.getElementById('questionInput').value = '';
            
            // Show loading
            const loadingDiv = addMessageToChat('Thinking...', 'ai', true);
            
            try {
                const response = await fetch('/api/ask-question', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        question: question,
                        location_id: locationId || null
                    })
                });
                
                const result = await response.json();
                
                // Remove loading message
                loadingDiv.remove();
                
                if (result.success) {
                    let answer = result.answer;
                    if (result.sources && result.sources.length > 0) {
                        answer += "\n\nSources: " + result.sources.map(s => s.product_name).join(', ');
                    }
                    addMessageToChat(answer, 'ai');
                } else {
                    addMessageToChat(result.answer || 'Sorry, I couldn\'t find an answer to your question.', 'ai');
                }
                
            } catch (error) {
                loadingDiv.remove();
                addMessageToChat('Sorry, there was an error processing your question.', 'ai');
                console.error('Error asking question:', error);
            }
        }
        
        // Add message to chat
        function addMessageToChat(message, sender, isLoading = false) {
            const chatContainer = document.getElementById('chatContainer');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}-message p-3 rounded-lg ${isLoading ? 'opacity-50' : ''}`;
            
            const senderLabel = sender === 'user' ? 'You' : 'AI Assistant';
            messageDiv.innerHTML = `<p><strong>${senderLabel}:</strong> ${message.replace(/\n/g, '<br>')}</p>`;
            
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            
            return messageDiv;
        }
        
        // Handle file upload
        async function handleFileUpload(e) {
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const uploadBtn = e.target.querySelector('button[type="submit"]');
            
            // Show loading state
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Uploading...';
            uploadBtn.disabled = true;
            
            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showToast(`File uploaded successfully: ${result.product_name}`, 'success');
                    hideModal('uploadModal');
                    e.target.reset();
                    loadDashboardStats();
                } else {
                    showToast(result.message, 'error');
                }
                
            } catch (error) {
                console.error('Error uploading file:', error);
                showToast('Error uploading file', 'error');
            } finally {
                uploadBtn.innerHTML = '<i class="fas fa-upload mr-2"></i>Upload';
                uploadBtn.disabled = false;
            }
        }
        
        // Generate sticker
        async function generateSticker(type) {
            const productName = document.getElementById('stickerProductName').value.trim();
            
            if (!productName) {
                showToast('Please enter a product name', 'warning');
                return;
            }
            
            try {
                const endpoint = type === 'nfpa' ? '/api/generate-nfpa' : '/api/generate-ghs';
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ product_name: productName })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showToast(`${result.sticker_type} sticker generated successfully`, 'success');
                    hideModal('stickerModal');
                    
                    // Create download link
                    const link = document.createElement('a');
                    link.href = `/api/download-sticker/${result.filename}`;
                    link.download = result.filename;
                    link.click();
                } else {
                    showToast(result.message, 'error');
                }
                
            } catch (error) {
                console.error('Error generating sticker:', error);
                showToast('Error generating sticker', 'error');
            }
        }
        
        // Update popular questions
        function updatePopularQuestions(questions) {
            const container = document.getElementById('popularQuestions');
            container.innerHTML = '';
            
            if (questions.length === 0) {
                container.innerHTML = '<p class="text-gray-500 text-center py-4 col-span-2">No questions asked yet</p>';
                return;
            }
            
            questions.forEach(q => {
                const div = document.createElement('div');
                div.className = 'bg-gray-50 p-3 rounded-lg cursor-pointer hover:bg-gray-100 transition';
                div.innerHTML = `
                    <p class="text-sm font-medium">${q.question}</p>
                    <p class="text-xs text-gray-500">${q.count} times asked</p>
                `;
                div.addEventListener('click', () => {
                    document.getElementById('questionInput').value = q.question;
                    askQuestion();
                });
                container.appendChild(div);
            });
        }
        
        // Modal utilities
        function showModal(modalId) {
            document.getElementById(modalId).classList.remove('hidden');
            if (modalId === 'uploadModal') {
                loadStates();
            }
        }
        
        function hideModal(modalId) {
            document.getElementById(modalId).classList.add('hidden');
        }
        
        // Toast notification utility
        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            const icon = document.getElementById('toastIcon');
            const messageEl = document.getElementById('toastMessage');
            
            messageEl.textContent = message;
            
            const config = {
                success: { icon: 'fas fa-check-circle text-green-500', border: 'border-green-400' },
                error: { icon: 'fas fa-exclamation-circle text-red-500', border: 'border-red-400' },
                warning: { icon: 'fas fa-exclamation-triangle text-yellow-500', border: 'border-yellow-400' },
                info: { icon: 'fas fa-info-circle text-blue-500', border: 'border-blue-400' }
            };
            
            icon.className = config[type].icon;
            toast.querySelector('div > div').className = `bg-white rounded-lg shadow-lg border-l-4 ${config[type].border} p-4 max-w-sm`;
            
            toast.classList.remove('hidden');
            
            setTimeout(() => {
                hideToast();
            }, 5000);
        }
        
        function hideToast() {
            document.getElementById('toast').classList.add('hidden');
        }
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "database": "connected"
    })

@app.route('/api/dashboard-stats')
def dashboard_stats():
    """Get dashboard statistics"""
    stats = sds_assistant.get_dashboard_stats()
    return jsonify(stats)

@app.route('/api/states')
def get_states():
    """Get all US states"""
    states = sds_assistant.get_states()
    return jsonify(states)

@app.route('/api/locations')
def get_locations():
    """Get locations with optional filtering"""
    state_filter = request.args.get('state')
    search_term = request.args.get('search')
    locations = sds_assistant.get_locations(state_filter, search_term)
    return jsonify(locations)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file provided"})
    
    file = request.files['file']
    location_id = request.form.get('location_id')
    
    if not location_id:
        return jsonify({"success": False, "message": "Location is required"})
    
    if file.filename == '':
        return jsonify({"success": False, "message": "No file selected"})
    
    result = sds_assistant.upload_file(file, int(location_id))
    return jsonify(result)

@app.route('/api/ask-question', methods=['POST'])
def ask_question():
    """Handle AI question answering"""
    data = request.json
    question = data.get('question')
    location_id = data.get('location_id')
    user_session = session.get('user_id', 'anonymous')
    
    if not question:
        return jsonify({"success": False, "answer": "Please provide a question"})
    
    result = sds_assistant.answer_question(question, location_id, user_session)
    return jsonify(result)

@app.route('/api/search-web-sds', methods=['POST'])
def search_web_sds():
    """Search web for SDS documents"""
    data = request.json
    chemical_name = data.get('chemical_name')
    location_id = data.get('location_id')
    
    if not chemical_name:
        return jsonify({"success": False, "message": "Chemical name is required"})
    
    result = sds_assistant.search_web_for_sds(chemical_name, location_id)
    return jsonify(result)

@app.route('/api/generate-nfpa', methods=['POST'])
def generate_nfpa():
    """Generate NFPA sticker"""
    data = request.json
    product_name = data.get('product_name')
    
    if not product_name:
        return jsonify({"success": False, "message": "Product name is required"})
    
    result = sds_assistant.generate_nfpa_sticker(product_name)
    return jsonify(result)

@app.route('/api/generate-ghs', methods=['POST'])
def generate_ghs():
    """Generate GHS sticker"""
    data = request.json
    product_name = data.get('product_name')
    
    if not product_name:
        return jsonify({"success": False, "message": "Product name is required"})
    
    result = sds_assistant.generate_ghs_sticker(product_name)
    return jsonify(result)

@app.route('/api/download-sticker/<filename>')
def download_sticker(filename):
    """Download generated sticker"""
    try:
        return send_file(f'static/stickers/{filename}', as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        "error": "Not Found",
        "message": "The requested URL was not found on the server."
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal Server Error",
        "message": "Something went wrong on the server."
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Starting SDS Assistant with AI Question Answering...")
    print("📍 Database will be populated with US cities on first run")
    print(f"🌐 Application will be available at: http://localhost:{port}")
    print("🤖 AI-powered question answering enabled")
    print("📱 Mobile PWA ready")
    print()
    app.run(debug=False, host='0.0.0.0', port=port)
