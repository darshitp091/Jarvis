import os
import sqlite3
import pandas as pd
import numpy as np
from loguru import logger

class DataAnalyzer:
    """Ingests Excel, CSV, PDF, and Word documents; provides matplotlib plotting, statistical analysis, and KPI tracking."""

    def __init__(self, db_path: str = "config/kpis.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS kpi_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize KPI database: {e}")

    def read_document_text(self, filepath: str) -> str:
        """Parses PDF, CSV, Excel, or Word documents and returns their contents/summary."""
        path = os.path.abspath(os.path.expanduser(filepath))
        if not os.path.exists(path):
            return f"Sir, the file at {filepath} does not exist."
            
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                df = pd.read_csv(path)
                return f"CSV successfully read, sir. Shape is {df.shape[0]} rows by {df.shape[1]} columns. Columns: {', '.join(df.columns)}. Top rows:\n{df.head(3).to_string()}"
                
            elif ext in [".xls", ".xlsx"]:
                df = pd.read_excel(path)
                return f"Excel file successfully read, sir. Shape is {df.shape[0]} rows by {df.shape[1]} columns. Sheets present are handled. Top rows:\n{df.head(3).to_string()}"
                
            elif ext == ".pdf":
                import pypdf
                reader = pypdf.PdfReader(path)
                text = ""
                # Read up to first 5 pages to prevent buffer overflow
                pages_to_read = min(len(reader.pages), 5)
                for idx in range(pages_to_read):
                    text += reader.pages[idx].extract_text() or ""
                return f"PDF read complete, sir ({len(reader.pages)} pages). Extract of text:\n{text[:1200]}..."
                
            elif ext in [".doc", ".docx"]:
                import docx
                doc = docx.Document(path)
                text = "\n".join(p.text for p in doc.paragraphs[:25]) # read top paragraphs
                return f"Word document read complete, sir. Extract of text:\n{text[:1200]}..."
                
            else:
                # Text files
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)
                return f"Text document read complete, sir. Content:\n{content}..."
        except Exception as e:
            logger.error(f"Error parsing document: {e}")
            return f"Error reading document: {str(e)}"

    def create_chart(self, x_values: list, y_values: list, title: str, xlabel: str, ylabel: str, chart_type: str = "line", save_path: str = "config/chart.png") -> str:
        """Plots a chart and saves it locally in the config directory."""
        try:
            import matplotlib.pyplot as plt
            
            # Clear current figure
            plt.clf()
            
            # Convert list items to numeric if possible
            x_num = []
            for x in x_values:
                try: x_num.append(float(x))
                except ValueError: x_num.append(x)
            
            y_num = [float(y) for y in y_values]
            
            if chart_type == "bar":
                plt.bar(x_num, y_num, color='teal')
            elif chart_type == "scatter":
                plt.scatter(x_num, y_num, color='orange')
            else:
                plt.plot(x_num, y_num, marker='o', color='darkred', linewidth=2)
                
            plt.title(title, fontsize=14, fontweight='bold')
            plt.xlabel(xlabel)
            plt.ylabel(ylabel)
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.tight_layout()
            
            # Ensure folder exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            plt.savefig(save_path, dpi=150)
            plt.close()
            
            logger.info(f"Chart saved successfully at {save_path}")
            return f"Chart successfully generated and saved to {save_path}, sir."
        except Exception as e:
            logger.error(f"Matplotlib chart generation failed: {e}")
            return f"Failed to generate chart: {str(e)}"

    def calculate_statistics(self, filepath: str, column_name: str) -> str:
        """Loads a dataset (CSV/Excel) and calculates statistics and detects anomalies."""
        path = os.path.abspath(os.path.expanduser(filepath))
        if not os.path.exists(path):
            return f"File does not exist at {filepath}, sir."
            
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                df = pd.read_csv(path)
            elif ext in [".xls", ".xlsx"]:
                df = pd.read_excel(path)
            else:
                return "Statistical analysis requires a CSV or Excel dataset, sir."
                
            if column_name not in df.columns:
                return f"Column '{column_name}' not found. Available columns are: {', '.join(df.columns)}."
                
            # Drop NaN and convert to numeric
            data = pd.to_numeric(df[column_name].dropna(), errors='coerce').dropna()
            if data.empty:
                return f"No numeric data found in column '{column_name}', sir."
                
            mean = data.mean()
            median = data.median()
            std_dev = data.std()
            min_val = data.min()
            max_val = data.max()
            
            # Simple standard anomaly detection (elements 3 standard deviations away from the mean)
            anomalies = data[(data - mean).abs() > (2 * std_dev)]
            anomaly_summary = ""
            if not anomalies.empty:
                anomaly_summary = f"Detected {len(anomalies)} anomalies (values beyond 2 standard deviations):\n{anomalies.head(5).to_string()}"
            else:
                anomaly_summary = "No anomalies detected in the dataset."
                
            summary = (
                f"Statistical Analysis of '{column_name}':\n"
                f" - Count: {len(data)}\n"
                f" - Mean: {mean:.3f}\n"
                f" - Median: {median:.3f}\n"
                f" - Std Dev: {std_dev:.3f}\n"
                f" - Range: {min_val} to {max_val}\n"
                f"{anomaly_summary}"
            )
            return summary
        except Exception as e:
            logger.error(f"Statistics calculation failed: {e}")
            return f"Failed to compute statistics: {str(e)}"

    def log_kpi(self, name: str, value: float) -> str:
        """Saves a metric key-value pair to the local KPI sqlite table."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT INTO kpi_logs (metric_name, value) VALUES (?, ?)", (name, value))
            conn.commit()
            conn.close()
            logger.info(f"Logged KPI: {name} = {value}")
            return f"Logged metric '{name}' value {value} successfully, sir."
        except Exception as e:
            logger.error(f"KPI log failed: {e}")
            return f"Failed to log KPI: {str(e)}"

    def get_kpi_history(self, name: str) -> str:
        """Retrieves history and average value for a logged KPI."""
        try:
            conn = sqlite3.connect(self.db_path)
            df = pd.read_sql_query("SELECT timestamp, value FROM kpi_logs WHERE metric_name = ? ORDER BY timestamp DESC", conn, params=(name,))
            conn.close()
            
            if df.empty:
                return f"No logged history found for metric '{name}', sir."
                
            avg_val = df["value"].mean()
            history_rows = df.head(10).to_string(index=False)
            
            return f"KPI History for '{name}' (Average: {avg_val:.2f}):\n{history_rows}"
        except Exception as e:
            logger.error(f"KPI fetch failed: {e}")
            return f"Failed to fetch KPI history: {str(e)}"
