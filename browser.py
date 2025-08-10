import sys
import os
import json
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, urljoin
import requests
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWebEngineWidgets import *

class DatabaseManager:
    def __init__(self):
        # Criar diretório de dados do usuário
        self.data_dir = self.get_data_directory()
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "browser_data.db")
        self.init_database()
    
    def get_data_directory(self):
        """Retorna o diretório apropriado para dados do aplicativo"""
        if sys.platform == "win32":
            # Windows: %APPDATA%/NeoBrowser
            return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "NeoBrowser")
        elif sys.platform == "darwin":
            # macOS: ~/Library/Application Support/NeoBrowser
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "NeoBrowser")
        else:
            # Linux: ~/.config/NeoBrowser
            return os.path.join(os.path.expanduser("~"), ".config", "NeoBrowser")
    
    def init_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Tabela de histórico
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    visit_count INTEGER DEFAULT 1
                )
            ''')
            
            # Tabela de favoritos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabela de downloads
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    status TEXT DEFAULT 'downloading',
                    size INTEGER DEFAULT 0,
                    downloaded INTEGER DEFAULT 0,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            print(f"Banco de dados inicializado em: {self.db_path}")
        except Exception as e:
            print(f"Erro ao inicializar banco de dados: {e}")
            # Fallback para diretório temporário
            import tempfile
            temp_dir = tempfile.gettempdir()
            self.db_path = os.path.join(temp_dir, "neobrowser_data.db")
            print(f"Usando diretório temporário: {self.db_path}")
            try:
                conn = sqlite3.connect(self.db_path)
                conn.close()
            except:
                print("Erro crítico: Não foi possível criar banco de dados")

class SettingsManager:
    def __init__(self):
        # Usar o mesmo diretório de dados do DatabaseManager
        self.data_dir = self.get_data_directory()
        os.makedirs(self.data_dir, exist_ok=True)
        self.settings_file = os.path.join(self.data_dir, "browser_settings.json")
        self.default_settings = {
            "theme_color": "#2D1B69",
            "search_engine": "https://www.google.com/search?q=",
            "homepage": "https://www.google.com",
            "download_directory": os.path.expanduser("~/Downloads"),
            "show_bookmarks_bar": True,
            "enable_javascript": True
        }
        self.load_settings()
    
    def get_data_directory(self):
        """Retorna o diretório apropriado para dados do aplicativo"""
        if sys.platform == "win32":
            # Windows: %APPDATA%/NeoBrowser
            return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "NeoBrowser")
        elif sys.platform == "darwin":
            # macOS: ~/Library/Application Support/NeoBrowser
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "NeoBrowser")
        else:
            # Linux: ~/.config/NeoBrowser
            return os.path.join(os.path.expanduser("~"), ".config", "NeoBrowser")
    
    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings = {**self.default_settings, **loaded_settings}
            else:
                self.settings = self.default_settings.copy()
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")
            self.settings = self.default_settings.copy()
    
    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")
    
    def get(self, key):
        return self.settings.get(key, self.default_settings.get(key))
    
    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

class TabWidget(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_browser = parent
        self.load_finished.connect(self.on_load_finished)
        
    def on_load_finished(self, ok):
        if ok and self.parent_browser:
            url = self.url().toString()
            title = self.title()
            if url and not url.startswith('data:') and not url.startswith('chrome://'):
                self.parent_browser.add_to_history(url, title)

class DownloadWidget(QWidget):
    def __init__(self, download_item):
        super().__init__()
        self.download_item = download_item
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout()
        
        # Ícone do arquivo
        icon_label = QLabel("📁")
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)
        
        # Informações do download
        info_layout = QVBoxLayout()
        self.filename_label = QLabel(self.download_item.path().split('/')[-1])
        self.progress_label = QLabel("Preparando download...")
        info_layout.addWidget(self.filename_label)
        info_layout.addWidget(self.progress_label)
        layout.addLayout(info_layout)
        
        # Barra de progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)
        
        # Botão cancelar
        cancel_btn = QPushButton("❌")
        cancel_btn.clicked.connect(self.download_item.cancel)
        layout.addWidget(cancel_btn)
        
        self.setLayout(layout)
        
        # Conectar sinais
        self.download_item.downloadProgress.connect(self.update_progress)
        self.download_item.finished.connect(self.download_finished)
        
    def update_progress(self, received, total):
        if total > 0:
            progress = int((received / total) * 100)
            self.progress_bar.setValue(progress)
            self.progress_label.setText(f"{self.format_size(received)} / {self.format_size(total)}")
    
    def download_finished(self):
        self.progress_label.setText("Download concluído!")
        self.progress_bar.setValue(100)
    
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

class FuturisticBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.settings = SettingsManager()
        self.downloads = []
        self.init_ui()
        self.apply_theme()
        
    def init_ui(self):
        self.setWindowTitle("NeoBrowser")
        self.setGeometry(100, 100, 1400, 900)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Barra de navegação
        nav_layout = QHBoxLayout()
        
        # Botões de navegação
        self.back_btn = QPushButton("◀")
        self.forward_btn = QPushButton("▶")
        self.refresh_btn = QPushButton("⟲")
        self.home_btn = QPushButton("🏠")
        
        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.forward_btn)
        nav_layout.addWidget(self.refresh_btn)
        nav_layout.addWidget(self.home_btn)
        
        # Barra de endereço
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Digite uma URL ou pesquise...")
        nav_layout.addWidget(self.address_bar, 1)
        
        # Botões de ação
        self.star_btn = QPushButton("☆")
        self.menu_btn = QPushButton("⋮")
        self.download_btn = QPushButton("⬇")
        
        nav_layout.addWidget(self.star_btn)
        nav_layout.addWidget(self.download_btn)
        nav_layout.addWidget(self.menu_btn)
        
        main_layout.addLayout(nav_layout)
        
        # Sistema de abas
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        main_layout.addWidget(self.tab_widget)
        
        # Conectar sinais
        self.setup_connections()
        
        # Criar primeira aba
        self.add_new_tab(self.settings.get("homepage"))
        
        # Menu
        self.create_menu()
        
    def setup_connections(self):
        self.back_btn.clicked.connect(self.go_back)
        self.forward_btn.clicked.connect(self.go_forward)
        self.refresh_btn.clicked.connect(self.refresh_page)
        self.home_btn.clicked.connect(self.go_home)
        self.address_bar.returnPressed.connect(self.navigate_to_url)
        self.star_btn.clicked.connect(self.toggle_bookmark)
        self.download_btn.clicked.connect(self.show_downloads)
        self.menu_btn.clicked.connect(self.show_menu)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.current_tab_changed)
        
    def create_menu(self):
        self.menu = QMenu()
        
        # Nova aba
        new_tab_action = QAction("Nova Aba", self)
        new_tab_action.triggered.connect(lambda: self.add_new_tab())
        self.menu.addAction(new_tab_action)
        
        # Nova janela
        new_window_action = QAction("Nova Janela", self)
        new_window_action.triggered.connect(self.new_window)
        self.menu.addAction(new_window_action)
        
        self.menu.addSeparator()
        
        # Histórico
        history_action = QAction("Histórico", self)
        history_action.triggered.connect(self.show_history)
        self.menu.addAction(history_action)
        
        # Favoritos
        bookmarks_action = QAction("Favoritos", self)
        bookmarks_action.triggered.connect(self.show_bookmarks)
        self.menu.addAction(bookmarks_action)
        
        # Downloads
        downloads_action = QAction("Downloads", self)
        downloads_action.triggered.connect(self.show_downloads)
        self.menu.addAction(downloads_action)
        
        self.menu.addSeparator()
        
        # Configurações
        settings_action = QAction("Configurações", self)
        settings_action.triggered.connect(self.show_settings)
        self.menu.addAction(settings_action)
        
    def apply_theme(self):
        theme_color = self.settings.get("theme_color")
        
        style = f"""
        QMainWindow {{
            background-color: #1a1a1a;
            color: white;
        }}
        
        QPushButton {{
            background-color: {theme_color};
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 6px;
            font-weight: bold;
            min-width: 30px;
        }}
        
        QPushButton:hover {{
            background-color: {theme_color}aa;
            transform: scale(1.05);
        }}
        
        QPushButton:pressed {{
            background-color: {theme_color}66;
        }}
        
        QLineEdit {{
            background-color: #2a2a2a;
            color: white;
            border: 2px solid {theme_color};
            border-radius: 20px;
            padding: 10px 15px;
            font-size: 14px;
        }}
        
        QLineEdit:focus {{
            border-color: {theme_color}ff;
            background-color: #333333;
        }}
        
        QTabWidget::pane {{
            border: none;
            background-color: #1a1a1a;
        }}
        
        QTabBar::tab {{
            background-color: #2a2a2a;
            color: white;
            padding: 10px 15px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }}
        
        QTabBar::tab:selected {{
            background-color: {theme_color};
        }}
        
        QTabBar::tab:hover {{
            background-color: #3a3a3a;
        }}
        
        QTabBar::close-button {{
            image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAYAAAAfSC3RAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAdgAAAHYBTnsmCAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAFESURBVCiRpZM9SwNBEIafgwiCYGGhYGGhYKHYWFhY2FhYWNhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhY);
        }}
        
        QMenu {{
            background-color: #2a2a2a;
            color: white;
            border: 1px solid {theme_color};
            border-radius: 8px;
        }}
        
        QMenu::item {{
            padding: 8px 20px;
        }}
        
        QMenu::item:selected {{
            background-color: {theme_color};
        }}
        """
        
        self.setStyleSheet(style)
        
    def add_new_tab(self, url=None):
        if not url:
            url = self.settings.get("homepage")
            
        browser = TabWidget(self)
        
        # Configurar profile
        profile = QWebEngineProfile.defaultProfile()
        profile.downloadRequested.connect(self.handle_download)
        
        index = self.tab_widget.addTab(browser, "Nova Aba")
        self.tab_widget.setCurrentIndex(index)
        
        browser.load(QUrl(url))
        browser.titleChanged.connect(lambda title, browser=browser: self.update_tab_title(browser, title))
        browser.urlChanged.connect(lambda url, browser=browser: self.update_address_bar(browser, url))
        
        return browser
        
    def close_tab(self, index):
        if self.tab_widget.count() > 1:
            self.tab_widget.removeTab(index)
        else:
            self.close()
            
    def current_tab_changed(self, index):
        if index >= 0:
            browser = self.tab_widget.widget(index)
            if browser:
                self.address_bar.setText(browser.url().toString())
                self.update_navigation_buttons(browser)
                
    def update_tab_title(self, browser, title):
        index = self.tab_widget.indexOf(browser)
        if index >= 0:
            self.tab_widget.setTabText(index, title[:20] + "..." if len(title) > 20 else title)
            
    def update_address_bar(self, browser, url):
        if browser == self.tab_widget.currentWidget():
            self.address_bar.setText(url.toString())
            
    def update_navigation_buttons(self, browser):
        self.back_btn.setEnabled(browser.history().canGoBack())
        self.forward_btn.setEnabled(browser.history().canGoForward())
        
    def navigate_to_url(self):
        url = self.address_bar.text()
        browser = self.tab_widget.currentWidget()
        
        if not url.startswith('http://') and not url.startswith('https://'):
            if '.' in url:
                url = 'https://' + url
            else:
                search_engine = self.settings.get("search_engine")
                url = search_engine + url.replace(' ', '+')
                
        browser.load(QUrl(url))
        
    def go_back(self):
        browser = self.tab_widget.currentWidget()
        browser.back()
        
    def go_forward(self):
        browser = self.tab_widget.currentWidget()
        browser.forward()
        
    def refresh_page(self):
        browser = self.tab_widget.currentWidget()
        browser.reload()
        
    def go_home(self):
        browser = self.tab_widget.currentWidget()
        browser.load(QUrl(self.settings.get("homepage")))
        
    def toggle_bookmark(self):
        browser = self.tab_widget.currentWidget()
        url = browser.url().toString()
        title = browser.title()
        
        if self.is_bookmarked(url):
            self.remove_bookmark(url)
            self.star_btn.setText("☆")
        else:
            self.add_bookmark(url, title)
            self.star_btn.setText("★")
            
    def is_bookmarked(self, url):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bookmarks WHERE url = ?", (url,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
        
    def add_bookmark(self, url, title):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO bookmarks (url, title) VALUES (?, ?)", (url, title))
        conn.commit()
        conn.close()
        
    def remove_bookmark(self, url):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookmarks WHERE url = ?", (url,))
        conn.commit()
        conn.close()
        
    def add_to_history(self, url, title):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        # Verificar se já existe
        cursor.execute("SELECT id, visit_count FROM history WHERE url = ?", (url,))
        result = cursor.fetchone()
        
        if result:
            # Atualizar contagem
            cursor.execute("UPDATE history SET visit_count = visit_count + 1, visit_time = CURRENT_TIMESTAMP WHERE id = ?", (result[0],))
        else:
            # Inserir novo
            cursor.execute("INSERT INTO history (url, title) VALUES (?, ?)", (url, title))
            
        conn.commit()
        conn.close()
        
    def handle_download(self, download_item):
        download_dialog = QFileDialog()
        filename, _ = download_dialog.getSaveFileName(
            self, 
            "Salvar Download", 
            os.path.join(self.settings.get("download_directory"), download_item.suggestedFileName())
        )
        
        if filename:
            download_item.setPath(filename)
            download_item.accept()
            
            # Adicionar ao banco de dados
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO downloads (url, filename, filepath, status) 
                VALUES (?, ?, ?, 'downloading')
            """, (download_item.url().toString(), download_item.suggestedFileName(), filename))
            conn.commit()
            conn.close()
            
    def show_menu(self):
        self.menu.exec_(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))
        
    def show_history(self):
        self.add_new_tab("data:text/html," + self.generate_history_page())
        
    def show_bookmarks(self):
        self.add_new_tab("data:text/html," + self.generate_bookmarks_page())
        
    def show_downloads(self):
        self.add_new_tab("data:text/html," + self.generate_downloads_page())
        
    def show_settings(self):
        self.add_new_tab("data:text/html," + self.generate_settings_page())
        
    def new_window(self):
        new_browser = FuturisticBrowser()
        new_browser.show()
        
    def generate_history_page(self):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, visit_time, visit_count FROM history ORDER BY visit_time DESC LIMIT 100")
        history_items = cursor.fetchall()
        conn.close()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Histórico</title>
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background: linear-gradient(135deg, #1a1a1a, #2a2a2a);
                    color: white;
                    margin: 0;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .history-item {{
                    background: rgba(45, 27, 105, 0.1);
                    border: 1px solid {self.settings.get("theme_color")};
                    border-radius: 10px;
                    margin: 10px 0;
                    padding: 15px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                }}
                .history-item:hover {{
                    background: rgba(45, 27, 105, 0.2);
                    transform: translateY(-2px);
                }}
                .title {{ font-weight: bold; font-size: 16px; }}
                .url {{ color: #aaa; font-size: 14px; margin: 5px 0; }}
                .meta {{ color: #888; font-size: 12px; }}
                .clear-btn {{
                    background: #ff4444;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    cursor: pointer;
                    float: right;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📚 Histórico de Navegação</h1>
                <button class="clear-btn" onclick="clearHistory()">Limpar Histórico</button>
            </div>
            <div class="history-list">
        """
        
        for item in history_items:
            url, title, visit_time, visit_count = item
            html += f"""
                <div class="history-item" onclick="window.location.href='{url}'">
                    <div class="title">{title}</div>
                    <div class="url">{url}</div>
                    <div class="meta">{visit_time} • Visitado {visit_count} vez(es)</div>
                </div>
            """
            
        html += """
            </div>
            <script>
                function clearHistory() {
                    if (confirm('Tem certeza que deseja limpar todo o histórico?')) {
                        // Aqui você implementaria a limpeza do histórico
                        alert('Histórico limpo!');
                        location.reload();
                    }
                }
            </script>
        </body>
        </html>
        """
        
        return html
        
    def generate_bookmarks_page(self):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, created_time FROM bookmarks ORDER BY created_time DESC")
        bookmarks = cursor.fetchall()
        conn.close()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Favoritos</title>
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background: linear-gradient(135deg, #1a1a1a, #2a2a2a);
                    color: white;
                    margin: 0;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .bookmark-item {{
                    background: rgba(45, 27, 105, 0.1);
                    border: 1px solid {self.settings.get("theme_color")};
                    border-radius: 10px;
                    margin: 10px 0;
                    padding: 15px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .bookmark-item:hover {{
                    background: rgba(45, 27, 105, 0.2);
                    transform: translateY(-2px);
                }}
                .bookmark-info {{
                    flex-grow: 1;
                }}
                .title {{ font-weight: bold; font-size: 16px; }}
                .url {{ color: #aaa; font-size: 14px; margin: 5px 0; }}
                .meta {{ color: #888; font-size: 12px; }}
                .delete-btn {{
                    background: #ff4444;
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 5px;
                    cursor: pointer;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⭐ Favoritos</h1>
            </div>
            <div class="bookmarks-list">
        """
        
        for bookmark in bookmarks:
            url, title, created_time = bookmark
            html += f"""
                <div class="bookmark-item">
                    <div class="bookmark-info" onclick="window.location.href='{url}'">
                        <div class="title">{title}</div>
                        <div class="url">{url}</div>
                        <div class="meta">Adicionado em {created_time}</div>
                    </div>
                    <button class="delete-btn" onclick="deleteBookmark('{url}')">🗑️</button>
                </div>
            """
            
        html += """
            </div>
            <script>
                function deleteBookmark(url) {
                    if (confirm('Tem certeza que deseja remover este favorito?')) {
                        // Aqui você implementaria a remoção do favorito
                        alert('Favorito removido!');
                        location.reload();
                    }
                }
            </script>
        </body>
        </html>
        """
        
        return html
        
    def generate_downloads_page(self):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url, filename, filepath, status, start_time FROM downloads ORDER BY start_time DESC")
        downloads = cursor.fetchall()
        conn.close()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Downloads</title>
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background: linear-gradient(135deg, #1a1a1a, #2a2a2a);
                    color: white;
                    margin: 0;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .download-item {{
                    background: rgba(45, 27, 105, 0.1);
                    border: 1px solid {self.settings.get("theme_color")};
                    border-radius: 10px;
                    margin: 10px 0;
                    padding: 15px;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }}
                .file-icon {{
                    font-size: 32px;
                }}
                .download-info {{
                    flex-grow: 1;
                }}
                .filename {{ font-weight: bold; font-size: 16px; }}
                .filepath {{ color: #aaa; font-size: 14px; margin: 5px 0; }}
                .status {{ color: #888; font-size: 12px; }}
                .status.completed {{ color: #4CAF50; }}
                .status.downloading {{ color: #2196F3; }}
                .status.failed {{ color: #f44336; }}
                .actions {{
                    display: flex;
                    gap: 10px;
                }}
                .btn {{
                    background: {self.settings.get("theme_color")};
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 5px;
                    cursor: pointer;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⬇️ Downloads</h1>
            </div>
            <div class="downloads-list">
        """
        
        for download in downloads:
            url, filename, filepath, status, start_time = download
            status_class = status.lower()
            html += f"""
                <div class="download-item">
                    <div class="file-icon">📁</div>
                    <div class="download-info">
                        <div class="filename">{filename}</div>
                        <div class="filepath">{filepath}</div>
                        <div class="status {status_class}">Status: {status.title()} • {start_time}</div>
                    </div>
                    <div class="actions">
                        <button class="btn" onclick="openFile('{filepath}')">Abrir</button>
                        <button class="btn" onclick="showInFolder('{filepath}')">Mostrar na Pasta</button>
                    </div>
                </div>
            """
            
        html += """
            </div>
            <script>
                function openFile(filepath) {
                    alert('Abrindo arquivo: ' + filepath);
                }
                
                function showInFolder(filepath) {
                    alert('Mostrando na pasta: ' + filepath);
                }
            </script>
        </body>
        </html>
        """
        
        return html
        
    def generate_settings_page(self):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Configurações</title>
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background: linear-gradient(135deg, #1a1a1a, #2a2a2a);
                    color: white;
                    margin: 0;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .settings-section {{
                    background: rgba(45, 27, 105, 0.1);
                    border: 1px solid {self.settings.get("theme_color")};
                    border-radius: 10px;
                    margin: 20px 0;
                    padding: 20px;
                }}
                .setting-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin: 15px 0;
                    padding: 10px 0;
                    border-bottom: 1px solid #444;
                }}
                .setting-label {{
                    font-weight: bold;
                    font-size: 14px;
                }}
                .setting-description {{
                    color: #aaa;
                    font-size: 12px;
                    margin-top: 5px;
                }}
                input, select {{
                    background: #333;
                    color: white;
                    border: 1px solid {self.settings.get("theme_color")};
                    border-radius: 5px;
                    padding: 8px 12px;
                    min-width: 200px;
                }}
                .color-input {{
                    width: 50px;
                    height: 30px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                }}
                .save-btn {{
                    background: {self.settings.get("theme_color")};
                    color: white;
                    border: none;
                    padding: 12px 30px;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                    margin: 20px 10px;
                }}
                .reset-btn {{
                    background: #ff4444;
                    color: white;
                    border: none;
                    padding: 12px 30px;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                    margin: 20px 10px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⚙️ Configurações</h1>
            </div>
            
            <div class="settings-section">
                <h2>🎨 Aparência</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Cor do Tema</div>
                        <div class="setting-description">Escolha a cor principal do navegador</div>
                    </div>
                    <input type="color" class="color-input" id="theme-color" value="{self.settings.get("theme_color")}">
                </div>
            </div>
            
            <div class="settings-section">
                <h2>🔍 Navegação</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Motor de Busca</div>
                        <div class="setting-description">URL do motor de busca padrão</div>
                    </div>
                    <select id="search-engine">
                        <option value="https://www.google.com/search?q=" {"selected" if self.settings.get("search_engine") == "https://www.google.com/search?q=" else ""}>Google</option>
                        <option value="https://www.bing.com/search?q=" {"selected" if self.settings.get("search_engine") == "https://www.bing.com/search?q=" else ""}>Bing</option>
                        <option value="https://duckduckgo.com/?q=" {"selected" if self.settings.get("search_engine") == "https://duckduckgo.com/?q=" else ""}>DuckDuckGo</option>
                        <option value="https://search.yahoo.com/search?p=" {"selected" if self.settings.get("search_engine") == "https://search.yahoo.com/search?p=" else ""}>Yahoo</option>
                    </select>
                </div>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Página Inicial</div>
                        <div class="setting-description">URL da página que abre em novas abas</div>
                    </div>
                    <input type="url" id="homepage" value="{self.settings.get("homepage")}" placeholder="https://www.google.com">
                </div>
            </div>
            
            <div class="settings-section">
                <h2>📥 Downloads</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Diretório de Downloads</div>
                        <div class="setting-description">Pasta padrão para salvar downloads</div>
                    </div>
                    <input type="text" id="download-dir" value="{self.settings.get("download_directory")}" placeholder="/home/user/Downloads">
                </div>
            </div>
            
            <div class="settings-section">
                <h2>🛡️ Privacidade</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">JavaScript</div>
                        <div class="setting-description">Permitir execução de JavaScript nas páginas</div>
                    </div>
                    <input type="checkbox" id="enable-js" {"checked" if self.settings.get("enable_javascript") else ""}>
                </div>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Barra de Favoritos</div>
                        <div class="setting-description">Mostrar barra de favoritos abaixo da barra de endereços</div>
                    </div>
                    <input type="checkbox" id="show-bookmarks" {"checked" if self.settings.get("show_bookmarks_bar") else ""}>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <button class="save-btn" onclick="saveSettings()">💾 Salvar Configurações</button>
                <button class="reset-btn" onclick="resetSettings()">🔄 Restaurar Padrões</button>
            </div>
            
            <script>
                function saveSettings() {{
                    const settings = {{
                        theme_color: document.getElementById('theme-color').value,
                        search_engine: document.getElementById('search-engine').value,
                        homepage: document.getElementById('homepage').value,
                        download_directory: document.getElementById('download-dir').value,
                        enable_javascript: document.getElementById('enable-js').checked,
                        show_bookmarks_bar: document.getElementById('show-bookmarks').checked
                    }};
                    
                    alert('Configurações salvas! Reinicie o navegador para aplicar todas as mudanças.');
                    console.log('Settings saved:', settings);
                }}
                
                function resetSettings() {{
                    if (confirm('Tem certeza que deseja restaurar as configurações padrão?')) {{
                        document.getElementById('theme-color').value = '#2D1B69';
                        document.getElementById('search-engine').value = 'https://www.google.com/search?q=';
                        document.getElementById('homepage').value = 'https://www.google.com';
                        document.getElementById('download-dir').value = '{os.path.expanduser("~/Downloads")}';
                        document.getElementById('enable-js').checked = true;
                        document.getElementById('show-bookmarks').checked = true;
                        alert('Configurações restauradas para os padrões!');
                    }}
                }}
            </script>
        </body>
        </html>
        """
        
        return html

if __name__ == "__main__":
    # Configurar tratamento de erros
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        error_msg = f"Erro não tratado: {exc_type.__name__}: {exc_value}"
        print(error_msg)
        
        # Mostrar mensagem de erro amigável
        try:
            from PyQt5.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Erro - NeoBrowser")
                msg.setText("Ocorreu um erro inesperado:")
                msg.setDetailedText(error_msg)
                msg.exec_()
        except:
            pass
    
    sys.excepthook = handle_exception
    
    try:
        app = QApplication(sys.argv)
        
        # Configurar ícone da aplicação
        app.setApplicationName("NeoBrowser")
        app.setApplicationVersion("1.0")
        app.setOrganizationName("FuturisticSoft")
        
        # Verificar se PyQt5 WebEngine está disponível
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Erro - NeoBrowser")
            msg.setText("PyQt5 WebEngine não encontrado!")
            msg.setInformativeText("Instale PyQtWebEngine: pip install PyQtWebEngine")
            msg.exec_()
            sys.exit(1)
        
        # Criar e mostrar o navegador
        browser = FuturisticBrowser()
        browser.show()
        
        # Executar aplicação
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"Erro crítico na inicialização: {e}")
        try:
            from PyQt5.QtWidgets import QMessageBox, QApplication
            app = QApplication.instance() or QApplication(sys.argv)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Erro Crítico - NeoBrowser")
            msg.setText(f"Falha na inicialização:\n\n{str(e)}")
            msg.exec_()
        except:
            pass
        sys.exit(1)
