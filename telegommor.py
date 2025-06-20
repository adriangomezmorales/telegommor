import sqlite3
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
from fpdf import FPDF
from io import BytesIO
import os
import re
import textwrap
import traceback
from PIL import Image
import unicodedata
import argparse
import chardet

# ====================== FUNCIONES AUXILIARES ======================
def safe_string(text):
    """Convierte texto a ASCII seguro manteniendo ñ y tildes simplificadas"""
    if not text:
        return ""
    
    try:
        # Conservar ñ y Ñ
        text = text.replace('ñ', 'n').replace('Ñ', 'N')
        text = text.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
        text = text.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
        
        # Filtrar caracteres
        text = ''.join(c for c in text if 32 <= ord(c) <= 126 or c in 'ñÑáéíóúÁÉÍÓÚ')
        return text
    except:
        return "[Texto no válido]"

def clean_contact_name(name):
    """Limpia nombres de contacto"""
    if not name:
        return "Contacto Desconocido"
    
    name = re.sub(r'[;]{2,}', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = safe_string(name)
    
    if len(name) > 50:
        name = name[:47] + "..."
    
    return name

def decode_message_data(data):
    """Decodifica datos binarios de mensajes de Telegram"""
    if data is None:
        return ""
    
    try:
        # Detectar la codificación automáticamente
        if isinstance(data, bytes):
            result = chardet.detect(data)
            encoding = result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
            
            # Intentar decodificar con la codificación detectada
            try:
                return data.decode(encoding, errors='replace')
            except:
                # Si falla, probar con UTF-8 y luego con Latin-1
                try:
                    return data.decode('utf-8', errors='replace')
                except:
                    return data.decode('latin-1', errors='replace')
        else:
            return str(data)
    except Exception as e:
        return f"[Error decodificando mensaje: {str(e)}]"

def get_chat_name(conn, uid):
    if uid in get_chat_name.cache:
        return get_chat_name.cache[uid]
    
    name = "Contacto Desconocido"
    try:
        queries = [
            ("SELECT name FROM users WHERE uid = ?", [abs(uid)]),
            ("SELECT name FROM chats WHERE uid = ?", [abs(uid)]),
            ("SELECT name FROM enc_chats WHERE uid = ?", [abs(uid)]),
            ("SELECT fname || ' ' || sname AS name FROM user_contacts_v7 WHERE uid = ?", [abs(uid)]),
        ]
        
        cursor = conn.cursor()
        for query, params in queries:
            try:
                cursor.execute(query, params)
                result = cursor.fetchone()
                if result and result[0]:
                    name = result[0]
                    break
            except:
                continue
        
        if name == "Contacto Desconocido":
            name = f"Contacto {uid}"
    except:
        name = f"Contacto {uid}"
    
    get_chat_name.cache[uid] = name
    return name

get_chat_name.cache = {}

def group_messages_by_contact_and_date(messages, conn):
    """Agrupa mensajes por contacto y luego por fecha"""
    conversations = {}
    
    for row in messages:
        mid, uid, date_ts, out, data = row
        chat_name = clean_contact_name(get_chat_name(conn, uid))
        
        if date_ts > 0:
            date_obj = datetime.fromtimestamp(date_ts)
            date_str = date_obj.strftime('%Y-%m-%d')
        else:
            date_str = "Fecha desconocida"
        
        if chat_name not in conversations:
            conversations[chat_name] = {}
        
        if date_str not in conversations[chat_name]:
            conversations[chat_name][date_str] = []
        
        timestamp = datetime.fromtimestamp(date_ts).strftime('%H:%M:%S') if date_ts > 0 else "Hora desconocida"
        
        # Decodificar el mensaje correctamente
        message_text = decode_message_data(data)
        message_text = safe_string(message_text)
        
        # CORRECCIÓN: Invertir la dirección de los mensajes
        is_outgoing = out == 1
        
        conversations[chat_name][date_str].append({
            'timestamp': timestamp,
            'is_outgoing': is_outgoing,
            'text': message_text,
            'raw_timestamp': date_ts
        })
    
    for contact in conversations:
        for date_str in conversations[contact]:
            conversations[contact][date_str].sort(key=lambda x: x['raw_timestamp'])
    
    sorted_contacts = sorted(conversations.keys())
    
    result = []
    for contact in sorted_contacts:
        contact_data = {
            'contact': contact,
            'dates': []
        }
        
        # Ordenar fechas de más antiguas a más recientes
        sorted_dates = sorted(
            conversations[contact].items(), 
            key=lambda x: datetime.strptime(x[0], '%Y-%m-%d') if x[0] != "Fecha desconocida" else datetime.min
        )
        
        for date_str, messages in sorted_dates:
            contact_data['dates'].append({
                'date': date_str,
                'messages': messages
            })
        
        result.append(contact_data)
    
    return result

# ====================== CLASES PRINCIPALES ======================
class PDFReport(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, 'Reporte Forense de Telegram', 0, 1, 'C')
        self.set_font('Helvetica', '', 10)
        self.cell(0, 8, f"Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'C')
        self.line(10, 25, self.w - 10, 25)
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')
    
    def add_section_title(self, title):
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 8, safe_string(title), 0, 1, 'L', 1)
        self.ln(2)
    
    def add_conversation_header(self, chat_name):
        self.set_font('Helvetica', 'B', 11)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 8, safe_string(f"Conversacion con: {chat_name}"), 0, 1, 'L', 1)
        self.ln(2)
    
    def add_date_header(self, date):
        self.set_font('Helvetica', '', 10)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 6, safe_string(f"Fecha: {date}"), 0, 1, 'L', 1)
        self.ln(1)
    
    def add_message(self, direction, contact, time, message):
        # Asegurarse que el mensaje no esté vacío
        if not message.strip():
            message = "[Mensaje vacio]"
        
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(50, 50, 50)
        header_text = safe_string(f"{direction} {contact} | {time}")
        self.cell(0, 5, header_text, 0, 1)
        
        self.set_font('Helvetica', '', 10)
        self.set_text_color(0, 0, 0)
        
        x = self.get_x() + 5
        self.set_x(x)
        
        # Usar texto seguro
        self.multi_cell(0, 6, message)
        
        self.ln(3)

# ====================== FUNCIÓN PRINCIPAL ======================
def generate_telegram_report(db_path, pdf_path):
    if not os.path.exists(db_path):
        print(f"Error: No se encontro el archivo {db_path}")
        return
    
    conn = None
    
    try:
        conn = sqlite3.connect(db_path)
        pdf = PDFReport()
        
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 24)
        pdf.cell(0, 40, safe_string("ANÁLISIS FORENSE DE TELEGRAM"), 0, 1, 'C')
        pdf.set_font('Helvetica', '', 16)
        pdf.cell(0, 20, safe_string("Análisis completo de la base de datos cache4.db"), 0, 1, 'C')
        
        pdf.add_page()
        pdf.add_section_title("Resumen Ejecutivo")
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM messages_v2")
            total_messages = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM dialogs")
            total_chats = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM media_v4")
            total_media = cursor.fetchone()[0] or 0
        except:
            total_users = "N/A"
            total_messages = "N/A"
            total_chats = "N/A"
            total_media = "N/A"
        
        pdf.set_font('Helvetica', '', 10)
        
        # Texto mejor formateado para el resumen
        intro_text = "Este reporte forense contiene un análisis completo de la base de datos de Telegram."
        pdf.multi_cell(0, 6, safe_string(intro_text))
        pdf.ln(4)
        
        key_elements = "Se han identificado los siguientes elementos clave:"
        pdf.multi_cell(0, 6, safe_string(key_elements))
        pdf.ln(4)
        
        # Lista de elementos clave con sangría
        pdf.set_x(20)  # Sangría para la lista
        pdf.cell(0, 6, safe_string(f"- Total de mensajes: {total_messages}"), 0, 1)
        pdf.set_x(20)
        pdf.cell(0, 6, safe_string(f"- Total de chats: {total_chats}"), 0, 1)
        pdf.set_x(20)
        pdf.cell(0, 6, safe_string(f"- Total de archivos multimedia: {total_media}"), 0, 1)
        pdf.ln(4)
        
        # Texto final
        conclusion_text = "A continuación se presenta un reporte de las conversaciones y contenido multimedia encontrado en la base de datos."
        pdf.multi_cell(0, 6, safe_string(conclusion_text))
        
        pdf.add_page()
        pdf.add_section_title("Mensajes Recientes")
        
        try:
            print("Extrayendo y agrupando mensajes...")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.mid, m.uid, m.date, m.out, m.data
                FROM messages_v2 m
                ORDER BY m.date DESC
            """)
            messages = cursor.fetchall()
            
            if messages:
                conversations = group_messages_by_contact_and_date(messages, conn)
                
                for contact_data in conversations:
                    pdf.add_conversation_header(contact_data['contact'])
                    
                    for date_data in contact_data['dates']:
                        pdf.add_date_header(date_data['date'])
                        
                        for message in date_data['messages']:
                            direction = "Para" if message['is_outgoing'] else "Desde"
                            
                            message_text = message['text']
                            
                            pdf.add_message(
                                direction=direction,
                                contact=contact_data['contact'],
                                time=message['timestamp'],
                                message=message_text
                            )
                    
                    pdf.ln(8)
            else:
                pdf.multi_cell(0, 6, safe_string("No se encontraron mensajes en la base de datos."))
                print("No se encontraron mensajes en la base de datos.")
        except Exception as e:
            error_msg = f"Error al recuperar mensajes: {str(e)}"
            pdf.multi_cell(0, 6, safe_string(error_msg))
            print(error_msg)
            traceback.print_exc()
        
        # Sección de estadísticas de actividad
        pdf.add_page()
        pdf.add_section_title("Estadísticas de Actividad")
        
        try:
            print("Generando estadísticas de actividad...")
            cursor = conn.cursor()
            cursor.execute("SELECT date FROM messages_v2 WHERE date > 0")
            timeline = cursor.fetchall()
            
            if timeline:
                dates = [datetime.fromtimestamp(row[0]) for row in timeline]
                hours = [d.hour for d in dates]
                hour_counts = pd.Series(hours).value_counts().sort_index()
                
                plt.figure(figsize=(10, 4))
                hour_counts.plot(kind='bar', color='skyblue')
                plt.title('Actividad de Mensajes por Hora del Dia')
                plt.xlabel('Hora del dia')
                plt.ylabel('Cantidad de mensajes')
                plt.xticks(rotation=0)
                plt.tight_layout()
                
                img_path = 'activity_chart.png'
                plt.savefig(img_path)
                plt.close()
                
                pdf.image(img_path, x=10, w=pdf.w - 20)
                os.remove(img_path)
            else:
                pdf.multi_cell(0, 6, safe_string("No hay datos para generar gráfico de actividad."))
                print("No hay datos para generar gráfico de actividad.")
        except Exception as e:
            error_msg = f"Error al generar gráfico de actividad: {str(e)}"
            pdf.multi_cell(0, 6, safe_string(error_msg))
            print(error_msg)
            traceback.print_exc()
        
        # Sección de información de sesión
        pdf.add_page()
        pdf.add_section_title("Información de Sesión")
        
        try:
            print("Extrayendo información de sesión...")
            cursor.execute("SELECT * FROM params")
            params = cursor.fetchone()
            
            if params:
                pdf.set_font('Helvetica', '', 10)
                pdf.multi_cell(0, 6, safe_string(f"""
                Información técnica de la sesión de Telegram:
                
                - Ultima secuencia: {params[1]}
                - PTS (Peer-to-peer timestamp): {params[2]}
                - QTS (Qts timestamp): {params[4]}
                - Ultima fecha de sincronizacion: {datetime.fromtimestamp(params[3]).strftime('%Y-%m-%d %H:%M:%S')}
                """))
            else:
                pdf.multi_cell(0, 6, safe_string("No se encontró información de sesión."))
                print("No se encontró información de sesión.")
        except Exception as e:
            error_msg = "No se pudo recuperar la información de sesión."
            pdf.multi_cell(0, 6, safe_string(error_msg))
            print(error_msg)
            traceback.print_exc()
        
        # Sección de conclusiones
        pdf.add_page()
        pdf.add_section_title("Conclusiones Forenses")
        
        pdf.set_font('Helvetica', '', 10)
        
        num_messages = len(messages) if messages else 0
        
        peak_hour = "N/A"
        if 'hour_counts' in locals() and not hour_counts.empty:
            try:
                peak_hour = hour_counts.idxmax()
            except:
                pass
        
        conclusion_text = f"""
        Análisis de los datos encontrados en la base de datos de Telegram:
        
        - Se analizó un total de {num_messages} mensajes
        
        Patrones de actividad:
        - Horario de mayor actividad: {peak_hour}:00
        """
        
        pdf.multi_cell(0, 6, safe_string(conclusion_text))
        
        print("Reporte completado, guardando PDF...")
        print("Herramienta creada por Adrián Gómez Morales")
        
        # Intentar guardar en ubicación alternativa si falla la principal
        try:
            pdf.output(pdf_path)
            print(f"Reporte generado en: {os.path.abspath(pdf_path)}")
        except Exception as e:
            print(f"Error al guardar en ruta principal: {str(e)}")
            
            # Intentar en ubicación alternativa
            alt_path = os.path.join(os.getcwd(), "telegram_forensic_alt.pdf")
            try:
                pdf.output(alt_path)
                print(f"Se guardó una versión alternativa en: {alt_path}")
            except Exception as alt_e:
                print(f"Error crítico al guardar el PDF: {str(alt_e)}")
                print("No se pudo guardar el reporte en ningún archivo.")
        
        print("Reporte completado")
        
    except Exception as e:
        print(f"Error general en el reporte: {str(e)}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

# ====================== MANEJO DE ARGUMENTOS ======================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generar reporte forense de Telegram')
    parser.add_argument('db_path', type=str, help='Ruta a la base de datos cache4.db')
    parser.add_argument('--output', type=str, default='telegram_forensic.pdf', 
                        help='Ruta de salida para el PDF (opcional)')
    
    args = parser.parse_args()
    
    print(f"Base de datos: {args.db_path}")
    print(f"Archivo de salida: {args.output}")
    
    print("Iniciando analisis forense de Telegram...")
    generate_telegram_report(args.db_path, args.output)
    print("Proceso completado.")
