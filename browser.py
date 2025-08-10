import sys
import os
import json
import sqlite3
import html
from urllib.parse import urlencode, parse_qs
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QTabWidget, QAction, QMenu, QFileDialog, QProgressBar,
    QMessageBox, QToolBar, QStyle, QShortcut
)
from PyQt5.QtCore import Qt, QUrl, QTimer, QObject, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QKeySequence, QDesktopServices

# Hint ao empacotador para incluir WebEngine no .exe
try:
    import PyQt5.QtWebEngineWidgets  # noqa: F401
    import PyQt5.QtWebEngineCore     # noqa: F401
    import PyQt5.QtWebEngine         # noqa: F401
except Exception:
    pass

APP_NAME = "Eirus Alpha"
PROVIDER = "Luan Chicale"


# ==========================
# Persistência e Configurações
# ==========================

class DatabaseManager:
    def __init__(self):
        self.data_dir = self.get_data_directory()
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "browser_data.db")
        self.init_database()

    def get_data_directory(self):
        base_name = "EirusAlpha"
        if sys.platform == "win32":
            return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", base_name)
        elif sys.platform == "darwin":
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", base_name)
        else:
            return os.path.join(os.path.expanduser("~"), ".config", base_name)

    def init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Histórico
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        visit_count INTEGER DEFAULT 1
                    )
                ''')
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_history_url ON history(url)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_visit_time ON history(visit_time)')
                # Favoritos
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bookmarks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON bookmarks(created_time)')
                # Downloads
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        filepath TEXT NOT NULL,
                        status TEXT DEFAULT 'downloading',
                        size INTEGER DEFAULT 0,
                        downloaded INTEGER DEFAULT 0,
                        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        end_time TIMESTAMP
                    )
                ''')
            print(f"Banco de dados inicializado em: {self.db_path}")
        except Exception as e:
            print(f"Erro ao inicializar banco de dados: {e}")
            import tempfile
            temp_dir = tempfile.gettempdir()
            self.db_path = os.path.join(temp_dir, "eirusalpha_data.db")
            try:
                with sqlite3.connect(self.db_path):
                    pass
            except Exception:
                print("Erro crítico: Não foi possível criar banco de dados")


class SettingsManager:
    def __init__(self):
        self.data_dir = self.get_data_directory()
        os.makedirs(self.data_dir, exist_ok=True)
        self.settings_file = os.path.join(self.data_dir, "browser_settings.json")
        self.default_settings = {
            "theme_color": "#2D1B69",
            "search_engine": "https://www.google.com/search?q=",
            "homepage": "https://www.google.com",
            "download_directory": os.path.expanduser("~/Downloads"),
            "show_bookmarks_bar": True,
            "enable_javascript": True,
            "restore_last_session": True,
            "last_session_tabs": []
        }
        self.load_settings()

    def get_data_directory(self):
        base_name = "EirusAlpha"
        if sys.platform == "win32":
            return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", base_name)
        elif sys.platform == "darwin":
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", base_name)
        else:
            return os.path.join(os.path.expanduser("~"), ".config", base_name)

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings = {**self.default_settings, **loaded}
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


# ==========================
# Widgets auxiliares
# ==========================

class DownloadItemModel(QObject):
    progressChanged = pyqtSignal(int, int)  # received, total
    statusChanged = pyqtSignal(str)         # 'downloading' | 'completed' | 'failed' | 'canceled'

    def __init__(self, download_item, db_path):
        super().__init__()
        self.item = download_item
        self.db_path = db_path
        self.download_id = None
        self._setup_db_record()
        self._connect_signals()

    def _setup_db_record(self):
        try:
            url = self.item.url().toString()
            suggested = self.item.suggestedFileName()
            path = self.item.path()
            total = int(getattr(self.item, "totalBytes", lambda: 0)() or 0)
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO downloads (url, filename, filepath, status, size, downloaded, start_time)
                    VALUES (?, ?, ?, 'downloading', ?, ?, CURRENT_TIMESTAMP)
                """, (url, suggested, path, total, 0))
                self.download_id = cur.lastrowid
                conn.commit()
        except Exception as e:
            print(f"Erro ao registrar download: {e}")

    def _connect_signals(self):
        try:
            self.item.downloadProgress.connect(self._on_progress)
            self.item.finished.connect(self._on_finished)
        except Exception as e:
            print(f"Erro ao conectar sinais de download: {e}")

    def _on_progress(self, received, total):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("UPDATE downloads SET downloaded = ?, size = ? WHERE id = ?", (int(received), int(total), self.download_id))
                conn.commit()
            self.progressChanged.emit(received, total)
        except Exception as e:
            print(f"Erro ao atualizar progresso no DB: {e}")

    def _on_finished(self):
        status = "completed" if os.path.exists(self.item.path()) else "failed"
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("UPDATE downloads SET status = ?, end_time = CURRENT_TIMESTAMP WHERE id = ?", (status, self.download_id))
                conn.commit()
            self.statusChanged.emit(status)
        except Exception as e:
            print(f"Erro ao finalizar download no DB: {e}")


class DownloadWidget(QWidget):
    def __init__(self, model: DownloadItemModel):
        super().__init__()
        self.model = model
        self.item = model.item
        self.setup_ui()
        self._connect()

    def setup_ui(self):
        layout = QHBoxLayout()
        icon_label = QLabel("📁")
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)

        info_layout = QVBoxLayout()
        self.filename_label = QLabel(os.path.basename(self.item.path()))
        self.progress_label = QLabel("Preparando download...")
        info_layout.addWidget(self.filename_label)
        info_layout.addWidget(self.progress_label)
        layout.addLayout(info_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)

        cancel_btn = QPushButton("❌")
        cancel_btn.clicked.connect(self.item.cancel)
        layout.addWidget(cancel_btn)

        self.setLayout(layout)

    def _connect(self):
        self.model.progressChanged.connect(self.update_progress)
        self.model.statusChanged.connect(self.update_status)

    def update_progress(self, received, total):
        if total > 0:
            progress = int((received / total) * 100)
            self.progress_bar.setValue(progress)
            self.progress_label.setText(f"{self._fmt(received)} / {self._fmt(total)}")
        else:
            self.progress_label.setText(self._fmt(received))

    def update_status(self, status):
        if status == "completed":
            self.progress_label.setText("Download concluído!")
            self.progress_bar.setValue(100)
        elif status == "failed":
            self.progress_label.setText("Falha no download.")
        elif status == "canceled":
            self.progress_label.setText("Download cancelado.")

    def _fmt(self, size):
        try:
            size = float(size)
        except Exception:
            return f"{size} B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ==========================
# Navegador
# ==========================

class FuturisticBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.settings = SettingsManager()
        self.download_models = []
        self.closed_tabs_stack = []  # para reabrir aba fechada
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_DesktopIcon))
        self.setGeometry(100, 100, 1400, 900)

        # UI
        self._init_ui()
        self.apply_theme()
        self._setup_shortcuts()

        # Abas iniciais
        initial_tabs = self.settings.get("last_session_tabs") if self.settings.get("restore_last_session") else []
        if initial_tabs:
            for url in initial_tabs:
                self.add_new_tab(url)
        else:
            self.add_new_tab(self.settings.get("homepage"))

    # -------- UI --------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)

        # Barra topo
        nav_layout = QHBoxLayout()
        self.back_btn = QPushButton("◀")
        self.forward_btn = QPushButton("▶")
        self.refresh_btn = QPushButton("⟲")
        self.home_btn = QPushButton("🏠")

        for btn in [self.back_btn, self.forward_btn, self.refresh_btn, self.home_btn]:
            btn.setCursor(Qt.PointingHandCursor)

        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.forward_btn)
        nav_layout.addWidget(self.refresh_btn)
        nav_layout.addWidget(self.home_btn)

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Digite uma URL ou pesquise...")
        nav_layout.addWidget(self.address_bar, 1)

        self.star_btn = QPushButton("☆")
        self.download_btn = QPushButton("⬇")
        self.menu_btn = QPushButton("⋮")
        nav_layout.addWidget(self.star_btn)
        nav_layout.addWidget(self.download_btn)
        nav_layout.addWidget(self.menu_btn)

        main_layout.addLayout(nav_layout)

        # Barra de favoritos (opcional)
        self.bookmarks_toolbar = QToolBar("Favoritos")
        self.bookmarks_toolbar.setIconSize(QSize(16, 16))
        main_layout.addWidget(self.bookmarks_toolbar)
        self.bookmarks_toolbar.setVisible(self.settings.get("show_bookmarks_bar"))
        self._reload_bookmarks_bar()

        # Abas
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        main_layout.addWidget(self.tab_widget)

        # Conexões
        self._setup_connections()
        self._create_menu()

        # Painel simples de downloads
        self.downloads_panel = QWidget()
        self.downloads_layout = QVBoxLayout()
        self.downloads_layout.setContentsMargins(10, 10, 10, 10)
        self.downloads_panel.setLayout(self.downloads_layout)
        self.downloads_panel.setVisible(False)
        main_layout.addWidget(self.downloads_panel)

    def _create_menu(self):
        self.menu = QMenu()

        new_tab_action = QAction("Nova Aba", self)
        new_tab_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tab_action.triggered.connect(lambda: self.add_new_tab())
        self.menu.addAction(new_tab_action)

        new_window_action = QAction("Nova Janela", self)
        new_window_action.triggered.connect(self.new_window)
        self.menu.addAction(new_window_action)

        reopen_action = QAction("Reabrir Aba Fechada", self)
        reopen_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        reopen_action.triggered.connect(self.reopen_closed_tab)
        self.menu.addAction(reopen_action)

        self.menu.addSeparator()

        history_action = QAction("Histórico", self)
        history_action.triggered.connect(self.show_history)
        self.menu.addAction(history_action)

        bookmarks_action = QAction("Favoritos", self)
        bookmarks_action.triggered.connect(self.show_bookmarks)
        self.menu.addAction(bookmarks_action)

        downloads_action = QAction("Downloads", self)
        downloads_action.triggered.connect(self.show_downloads)
        self.menu.addAction(downloads_action)

        self.menu.addSeparator()

        settings_action = QAction("Configurações", self)
        settings_action.triggered.connect(self.show_settings)
        self.menu.addAction(settings_action)

        self.menu.addSeparator()

        about_action = QAction("Sobre", self)
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)

    def _setup_connections(self):
        self.back_btn.clicked.connect(self.go_back)
        self.forward_btn.clicked.connect(self.go_forward)
        self.refresh_btn.clicked.connect(self.refresh_page)
        self.home_btn.clicked.connect(self.go_home)
        self.address_bar.returnPressed.connect(self.navigate_to_url)
        self.star_btn.clicked.connect(self.toggle_bookmark)
        self.download_btn.clicked.connect(self.toggle_downloads_panel)
        self.menu_btn.clicked.connect(self.show_menu)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.current_tab_changed)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.address_bar.setFocus)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=lambda: self.close_tab(self.tab_widget.currentIndex()))
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.refresh_page)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_page)
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=self._prev_tab)

    def _next_tab(self):
        if self.tab_widget.count() == 0:
            return
        i = (self.tab_widget.currentIndex() + 1) % self.tab_widget.count()
        self.tab_widget.setCurrentIndex(i)

    def _prev_tab(self):
        if self.tab_widget.count() == 0:
            return
        i = (self.tab_widget.currentIndex() - 1) % self.tab_widget.count()
        self.tab_widget.setCurrentIndex(i)

    # -------- Aparência --------
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
        QToolBar {{
            background-color: #1e1e1e;
            border: none;
        }}
        """
        self.setStyleSheet(style)

    # -------- Abas --------
    def add_new_tab(self, url=None):
        if not url:
            url = self.settings.get("homepage")

        # Import tardio do WebEngine
        from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage, QWebEngineSettings

        parent_browser = self

        class CustomPage(QWebEnginePage):
            def acceptNavigationRequest(self, qurl, nav_type, is_main_frame):
                if qurl.scheme().lower() == "eirus":
                    self._handle_internal_action(qurl)
                    return False
                return super().acceptNavigationRequest(qurl, nav_type, is_main_frame)

            def createWindow(self, _type):
                new_view = parent_browser.add_new_tab()
                return new_view.page()

            def _handle_internal_action(self, qurl: QUrl):
                path = qurl.path().lstrip("/")
                params = parse_qs(qurl.query())
                if path == "clear-history":
                    parent_browser._clear_history()
                    parent_browser.show_history()
                elif path == "delete-bookmark":
                    burl = params.get("url", [""])[0]
                    if burl:
                        parent_browser.remove_bookmark(burl)
                        parent_browser._reload_bookmarks_bar()
                        parent_browser.show_bookmarks()
                elif path == "open-file":
                    filepath = params.get("filepath", [""])[0]
                    if filepath and os.path.exists(filepath):
                        QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))
                elif path == "show-in-folder":
                    filepath = params.get("filepath", [""])[0]
                    if filepath and os.path.exists(filepath):
                        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(filepath)))
                elif path == "save-settings":
                    try:
                        theme = params.get("theme_color", ["#2D1B69"])[0]
                        se = params.get("search_engine", ["https://www.google.com/search?q="])[0]
                        home = params.get("homepage", ["https://www.google.com"])[0]
                        ddir = params.get("download_directory", [os.path.expanduser("~/Downloads")])[0]
                        js = params.get("enable_javascript", ["true"])[0].lower() == "true"
                        bar = params.get("show_bookmarks_bar", ["true"])[0].lower() == "true"
                        parent_browser.settings.set("theme_color", theme)
                        parent_browser.settings.set("search_engine", se)
                        parent_browser.settings.set("homepage", home)
                        parent_browser.settings.set("download_directory", ddir)
                        parent_browser.settings.set("enable_javascript", js)
                        parent_browser.settings.set("show_bookmarks_bar", bar)
                        parent_browser.apply_theme()
                        parent_browser.bookmarks_toolbar.setVisible(bar)
                        parent_browser._apply_engine_settings_to_all()
                        parent_browser._reload_bookmarks_bar()
                        QMessageBox.information(parent_browser, APP_NAME, "Configurações salvas.")
                    except Exception as e:
                        QMessageBox.critical(parent_browser, APP_NAME, f"Falha ao salvar configurações: {e}")

            def certificateError(self, error):
                # Em algumas versões, retornar True aceita; False bloqueia
                msg = QMessageBox(parent_browser)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle(f"{APP_NAME} - Certificado inválido")
                msg.setText("O certificado do site é inválido ou não confiável.")
                msg.setInformativeText("Deseja continuar mesmo assim?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                res = msg.exec_()
                return res == QMessageBox.Yes

        # View
        view = QWebEngineView()
        page = CustomPage(view)
        view.setPage(page)

        # Perfil persistente
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(os.path.join(self.db.data_dir, "profile"))
        profile.setCachePath(os.path.join(self.db.data_dir, "cache"))
        try:
            if hasattr(profile, "setDownloadPath"):
                profile.setDownloadPath(self.settings.get("download_directory"))
        except Exception:
            pass
        try:
            if hasattr(QWebEngineProfile, "ForcePersistentCookies"):
                profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        except Exception:
            pass

        # Downloads (garante apenas uma conexão)
        try:
            try:
                profile.downloadRequested.disconnect()
            except Exception:
                pass
            profile.downloadRequested.connect(self.handle_download)
        except Exception as e:
            print(f"Aviso: Não foi possível conectar downloads: {e}")

        # Configurações da Engine
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, self.settings.get("enable_javascript"))
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

        # Aviso para HTTP puro
        def _warn_http(u: QUrl):
            if u.scheme().lower() == "http":
                self.statusBar().showMessage("Conexão não segura (HTTP).", 5000)
        view.urlChanged.connect(_warn_http)

        index = self.tab_widget.addTab(view, "Nova Aba")
        self.tab_widget.setCurrentIndex(index)

        # Sinais da aba
        view.titleChanged.connect(lambda t, v=view: self.update_tab_title(v, t))
        view.urlChanged.connect(lambda u, v=view: self.update_address_bar(v, u))
        view.iconChanged.connect(lambda i, v=view: self._update_tab_icon(v, i))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(v, ok))
        view.page().windowCloseRequested.connect(lambda v=view: self._close_view(v))

        # Carregar URL
        try:
            view.load(QUrl(url))
        except Exception as e:
            print(f"Erro ao carregar URL: {e}")
            view.setHtml(self._simple_welcome_page())

        return view

    def _close_view(self, view):
        idx = self.tab_widget.indexOf(view)
        if idx != -1:
            self.close_tab(idx)

    def closeEvent(self, event):
        try:
            tabs = []
            for i in range(self.tab_widget.count()):
                w = self.tab_widget.widget(i)
                if hasattr(w, "url"):
                    tabs.append(w.url().toString())
            self.settings.set("last_session_tabs", tabs)
        except Exception as e:
            print(f"Erro ao salvar sessão: {e}")
        super().closeEvent(event)

    def close_tab(self, index):
        if index >= 0 and self.tab_widget.count() > 0:
            w = self.tab_widget.widget(index)
            try:
                if hasattr(w, "url"):
                    self.closed_tabs_stack.append(w.url().toString())
            except Exception:
                pass
            self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self.close()

    def reopen_closed_tab(self):
        if self.closed_tabs_stack:
            url = self.closed_tabs_stack.pop()
            self.add_new_tab(url)

    def current_tab_changed(self, index):
        if index >= 0:
            view = self.tab_widget.widget(index)
            if view:
                try:
                    self.address_bar.setText(view.url().toString())
                    self.update_navigation_buttons(view)
                    self._update_star_state(view)
                except Exception:
                    pass

    def update_tab_title(self, view, title):
        index = self.tab_widget.indexOf(view)
        if index >= 0:
            title = title or ""
            self.tab_widget.setTabText(index, (title[:20] + "...") if len(title) > 20 else title)

    def _update_tab_icon(self, view, icon):
        index = self.tab_widget.indexOf(view)
        if index >= 0:
            self.tab_widget.setTabIcon(index, icon)

    def update_address_bar(self, view, url):
        if view == self.tab_widget.currentWidget():
            self.address_bar.setText(url.toString())
            self._update_star_state(view)
            self.update_navigation_buttons(view)

    def update_navigation_buttons(self, view):
        try:
            hist = view.history()
            self.back_btn.setEnabled(hist.canGoBack())
            self.forward_btn.setEnabled(hist.canGoForward())
        except Exception:
            self.back_btn.setEnabled(False)
            self.forward_btn.setEnabled(False)

    def _on_load_finished(self, view, ok):
        if ok:
            try:
                url = view.url().toString()
                title = view.title() or url
                if url and not url.startswith('data:') and not url.startswith('chrome://') and not url.startswith('eirus://'):
                    self.add_to_history(url, title)
            except Exception as e:
                print(f"Erro ao adicionar ao histórico: {e}")
        self.update_navigation_buttons(view)

    # -------- Navegação --------
    def navigate_to_url(self):
        url_text = self.address_bar.text().strip()
        view = self.tab_widget.currentWidget()
        if not view or not hasattr(view, 'load'):
            QMessageBox.warning(self, APP_NAME, "Aba atual inválida.")
            return

        try:
            if not url_text.startswith('http://') and not url_text.startswith('https://'):
                if '.' in url_text and ' ' not in url_text:
                    url_text = 'https://' + url_text
                else:
                    search_engine = self.settings.get("search_engine")
                    url_text = search_engine + url_text.replace(' ', '+')
            view.load(QUrl(url_text))
        except Exception as e:
            print(f"Erro ao navegar para URL: {e}")

    def go_back(self):
        view = self.tab_widget.currentWidget()
        if view and hasattr(view, 'back'):
            try:
                view.back()
            except Exception as e:
                print(f"Erro ao voltar: {e}")

    def go_forward(self):
        view = self.tab_widget.currentWidget()
        if view and hasattr(view, 'forward'):
            try:
                view.forward()
            except Exception as e:
                print(f"Erro ao avançar: {e}")

    def refresh_page(self):
        view = self.tab_widget.currentWidget()
        if view and hasattr(view, 'reload'):
            try:
                view.reload()
            except Exception as e:
                print(f"Erro ao recarregar: {e}")

    def go_home(self):
        view = self.tab_widget.currentWidget()
        if view and hasattr(view, 'load'):
            try:
                view.load(QUrl(self.settings.get("homepage")))
            except Exception as e:
                print(f"Erro ao ir para home: {e}")

    # -------- Favoritos --------
    def toggle_bookmark(self):
        view = self.tab_widget.currentWidget()
        if not view:
            return
        url = view.url().toString()
        title = view.title() or url

        if self.is_bookmarked(url):
            self.remove_bookmark(url)
            self.star_btn.setText("☆")
        else:
            self.add_bookmark(url, title)
            self.star_btn.setText("★")
        self._reload_bookmarks_bar()

    def _update_star_state(self, view):
        try:
            url = view.url().toString()
            self.star_btn.setText("★" if self.is_bookmarked(url) else "☆")
        except Exception:
            self.star_btn.setText("☆")

    def is_bookmarked(self, url):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM bookmarks WHERE url = ?", (url,))
            count = cur.fetchone()[0]
            return count > 0

    def add_bookmark(self, url, title):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO bookmarks (url, title) VALUES (?, ?)", (url, title))
            conn.commit()

    def remove_bookmark(self, url):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM bookmarks WHERE url = ?", (url,))
            conn.commit()

    def _reload_bookmarks_bar(self):
        self.bookmarks_toolbar.clear()
        if not self.settings.get("show_bookmarks_bar"):
            return
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT url, title FROM bookmarks ORDER BY created_time DESC LIMIT 20")
                for url, title in cur.fetchall():
                    action = QAction(QIcon(), title[:24] + ("..." if len(title) > 24 else ""), self)
                    action.triggered.connect(lambda checked=False, u=url: self._open_url_in_current(u))
                    self.bookmarks_toolbar.addAction(action)
        except Exception as e:
            print(f"Erro ao recarregar barra de favoritos: {e}")

    def _open_url_in_current(self, url):
        view = self.tab_widget.currentWidget()
        if view:
            view.load(QUrl(url))

    # -------- Histórico --------
    def add_to_history(self, url, title):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO history (url, title, visit_time, visit_count)
                VALUES (?, ?, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(url) DO UPDATE SET visit_count = visit_count + 1, visit_time = CURRENT_TIMESTAMP, title = excluded.title
            """, (url, title))
            conn.commit()

    # -------- Downloads --------
    def handle_download(self, download_item):
        default_dir = self.settings.get("download_directory")
        os.makedirs(default_dir, exist_ok=True)
        suggested = download_item.suggestedFileName()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Download",
            os.path.join(default_dir, suggested)
        )

        if filename:
            download_item.setPath(filename)
            download_item.accept()

            model = DownloadItemModel(download_item, self.db.db_path)
            widget = DownloadWidget(model)
            self.download_models.append(model)
            self.downloads_layout.addWidget(widget)
            self.downloads_panel.setVisible(True)

            def _on_finished_status(status):
                if status == "completed":
                    self.statusBar().showMessage(f"Download concluído: {os.path.basename(filename)}", 5000)
                elif status == "failed":
                    self.statusBar().showMessage(f"Download falhou: {os.path.basename(filename)}", 5000)

            model.statusChanged.connect(_on_finished_status)

    def toggle_downloads_panel(self):
        self.downloads_panel.setVisible(not self.downloads_panel.isVisible())

    # -------- Páginas internas (HTML seguro) --------
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

    def show_about(self):
        QMessageBox.information(self, f"Sobre - {APP_NAME}",
                                f"{APP_NAME}\nFornecedor: {PROVIDER}\n\n"
                                "Navegador baseado em PyQt5/QtWebEngine.\n"
                                "Este é um build Alpha para testes.")

    def _clear_history(self):
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM history")
                conn.commit()
            QMessageBox.information(self, APP_NAME, "Histórico limpo com sucesso.")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Falha ao limpar histórico: {e}")

    def _safe(self, s):
        return html.escape(s or "")

    def generate_history_page(self):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT url, title, visit_time, visit_count FROM history ORDER BY visit_time DESC LIMIT 200")
            items = cur.fetchall()

        theme = self.settings.get("theme_color")
        rows = []
        for url, title, visit_time, visit_count in items:
            rows.append(f"""
                <div class="history-item" onclick="window.location.href='{self._safe(url)}'">
                    <div class="title">{self._safe(title)}</div>
                    <div class="url">{self._safe(url)}</div>
                    <div class="meta">{self._safe(str(visit_time))} • Visitado {int(visit_count)} vez(es)</div>
                </div>
            """)

        html_doc = f"""
        <!doctype html>
        <html><head><meta charset="utf-8"><title>Histórico</title>
        <style>
        body {{ font-family: 'Segoe UI', sans-serif; background:#121212; color:white; margin:0; padding:20px; }}
        .header {{ display:flex; align-items:center; justify-content:space-between; }}
        .btn {{ background:{theme}; color:white; border:none; padding:10px 16px; border-radius:6px; cursor:pointer; }}
        .history-item {{
            background: rgba(45,27,105,0.10); border:1px solid {theme}; border-radius:10px; margin:10px 0; padding:15px; cursor:pointer;
        }}
        .history-item:hover {{ background: rgba(45,27,105,0.20); }}
        .title {{ font-weight:bold; font-size:16px; }}
        .url {{ color:#aaa; font-size:14px; margin:5px 0; }}
        .meta {{ color:#888; font-size:12px; }}
        </style></head>
        <body>
            <div class="header">
                <h1>📚 Histórico de Navegação</h1>
                <button class="btn" onclick="if(confirm('Limpar todo o histórico?')) location.href='eirus://clear-history'">Limpar Histórico</button>
            </div>
            <div class="history-list">
                {''.join(rows) if rows else '<p>Nada por aqui ainda.</p>'}
            </div>
        </body></html>
        """
        return html_doc

    def generate_bookmarks_page(self):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT url, title, created_time FROM bookmarks ORDER BY created_time DESC")
            items = cur.fetchall()

        theme = self.settings.get("theme_color")
        rows = []
        for url, title, created_time in items:
            su = self._safe(url)
            st = self._safe(title)
            sc = self._safe(str(created_time))
            rows.append(f"""
                <div class="bookmark-item">
                    <div class="bookmark-info" onclick="window.location.href='{su}'">
                        <div class="title">{st}</div>
                        <div class="url">{su}</div>
                        <div class="meta">Adicionado em {sc}</div>
                    </div>
                    <button class="delete-btn" onclick="if(confirm('Remover favorito?')) location.href='eirus://delete-bookmark?{urlencode({'url': url})}'">🗑️</button>
                </div>
            """)

        html_doc = f"""
        <!doctype html>
        <html><head><meta charset="utf-8"><title>Favoritos</title>
        <style>
        body {{ font-family:'Segoe UI',sans-serif; background:#121212; color:white; margin:0; padding:20px; }}
        .header {{ text-align:center; margin-bottom:30px; }}
        .bookmark-item {{ background: rgba(45,27,105,0.10); border:1px solid {theme}; border-radius:10px; margin:10px 0; padding:15px; display:flex; justify-content:space-between; align-items:center; }}
        .bookmark-item:hover {{ background: rgba(45,27,105,0.20); }}
        .title {{ font-weight:bold; font-size:16px; }}
        .url {{ color:#aaa; font-size:14px; margin:5px 0; }}
        .meta {{ color:#888; font-size:12px; }}
        .delete-btn {{ background:#ff4444; color:white; border:none; padding:8px 12px; border-radius:5px; cursor:pointer; }}
        </style></head>
        <body>
            <div class="header"><h1>⭐ Favoritos</h1></div>
            <div class="bookmarks-list">
                {''.join(rows) if rows else '<p>Sem favoritos ainda.</p>'}
            </div>
        </body></html>
        """
        return html_doc

    def generate_downloads_page(self):
        with sqlite3.connect(self.db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT url, filename, filepath, status, start_time FROM downloads ORDER BY start_time DESC")
            items = cur.fetchall()
        theme = self.settings.get("theme_color")
        rows = []
        for url, filename, filepath, status, start_time in items:
            su = self._safe(url)
            sf = self._safe(filename)
            sp = self._safe(filepath)
            ss = self._safe(status)
            st = self._safe(str(start_time))
            rows.append(f"""
                <div class="download-item">
                    <div class="file-icon">📁</div>
                    <div class="download-info">
                        <div class="filename">{sf}</div>
                        <div class="filepath">{sp}</div>
                        <div class="status {ss}">Status: {ss.title()} • {st}</div>
                    </div>
                    <div class="actions">
                        <button class="btn" onclick="location.href='eirus://open-file?{urlencode({'filepath': filepath})}'">Abrir</button>
                        <button class="btn" onclick="location.href='eirus://show-in-folder?{urlencode({'filepath': filepath})}'">Mostrar na Pasta</button>
                    </div>
                </div>
            """)
        html_doc = f"""
        <!doctype html>
        <html><head><meta charset="utf-8"><title>Downloads</title>
        <style>
        body {{ font-family:'Segoe UI',sans-serif; background:#121212; color:white; margin:0; padding:20px; }}
        .header {{ text-align:center; margin-bottom:30px; }}
        .download-item {{ background: rgba(45,27,105,0.10); border:1px solid {theme}; border-radius:10px; margin:10px 0; padding:15px; display:flex; align-items:center; gap:15px; }}
        .file-icon {{ font-size:32px; }}
        .download-info {{ flex-grow:1; }}
        .filename {{ font-weight:bold; font-size:16px; }}
        .filepath {{ color:#aaa; font-size:14px; margin:5px 0; }}
        .status {{ color:#bbb; font-size:12px; }}
        .status.completed {{ color:#4CAF50; }}
        .status.downloading {{ color:#2196F3; }}
        .status.failed {{ color:#f44336; }}
        .actions {{ display:flex; gap:10px; }}
        .btn {{ background:{theme}; color:white; border:none; padding:8px 12px; border-radius:5px; cursor:pointer; }}
        </style></head>
        <body>
            <div class="header"><h1>⬇️ Downloads</h1></div>
            <div class="downloads-list">
                {''.join(rows) if rows else '<p>Nenhum download registrado.</p>'}
            </div>
        </body></html>
        """
        return html_doc

    def generate_settings_page(self):
        theme = self.settings.get("theme_color")
        se = self.settings.get("search_engine")
        home = self._safe(self.settings.get("homepage"))
        ddir = self._safe(self.settings.get("download_directory"))
        js_checked = "checked" if self.settings.get("enable_javascript") else ""
        bar_checked = "checked" if self.settings.get("show_bookmarks_bar") else ""

        def opt(val, label):
            sel = "selected" if se == val else ""
            return f'<option value="{val}" {sel}>{label}</option>'

        html_doc = f"""
        <!doctype html>
        <html><head><meta charset="utf-8"><title>Configurações</title>
        <style>
        body {{ font-family:'Segoe UI',sans-serif; background:#121212; color:white; margin:0; padding:20px; }}
        .header {{ text-align:center; margin-bottom:30px; }}
        .settings-section {{ background: rgba(45,27,105,0.10); border:1px solid {theme}; border-radius:10px; margin:20px 0; padding:20px; }}
        .setting-item {{ display:flex; justify-content:space-between; align-items:center; margin:15px 0; padding:10px 0; border-bottom:1px solid #444; }}
        .setting-label {{ font-weight:bold; font-size:14px; }}
        .setting-description {{ color:#aaa; font-size:12px; margin-top:5px; }}
        input, select {{ background:#333; color:white; border:1px solid {theme}; border-radius:5px; padding:8px 12px; min-width:200px; }}
        .color-input {{ width:50px; height:30px; border:none; border-radius:5px; cursor:pointer; }}
        .save-btn {{ background:{theme}; color:white; border:none; padding:12px 30px; border-radius:5px; cursor:pointer; font-size:16px; margin: 10px; }}
        .reset-btn {{ background:#ff4444; color:white; border:none; padding:12px 30px; border-radius:5px; cursor:pointer; font-size:16px; margin: 10px; }}
        </style></head>
        <body>
            <div class="header"><h1>⚙️ Configurações</h1></div>

            <div class="settings-section">
                <h2>🎨 Aparência</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Cor do Tema</div>
                        <div class="setting-description">Escolha a cor principal do navegador</div>
                    </div>
                    <input type="color" class="color-input" id="theme-color" value="{self._safe(theme)}">
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
                        {opt("https://www.google.com/search?q=", "Google")}
                        {opt("https://www.bing.com/search?q=", "Bing")}
                        {opt("https://duckduckgo.com/?q=", "DuckDuckGo")}
                        {opt("https://search.yahoo.com/search?p=", "Yahoo")}
                    </select>
                </div>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Página Inicial</div>
                        <div class="setting-description">URL da página que abre em novas abas</div>
                    </div>
                    <input type="url" id="homepage" value="{home}" placeholder="https://www.google.com">
                </div>
            </div>

            <div class="settings-section">
                <h2>📥 Downloads</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Diretório de Downloads</div>
                        <div class="setting-description">Pasta padrão para salvar downloads</div>
                    </div>
                    <input type="text" id="download-dir" value="{ddir}" placeholder="/home/user/Downloads">
                </div>
            </div>

            <div class="settings-section">
                <h2>🛡️ Privacidade</h2>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">JavaScript</div>
                        <div class="setting-description">Permitir execução de JavaScript nas páginas</div>
                    </div>
                    <input type="checkbox" id="enable-js" {js_checked}>
                </div>
                <div class="setting-item">
                    <div>
                        <div class="setting-label">Barra de Favoritos</div>
                        <div class="setting-description">Mostrar barra de favoritos abaixo da barra de endereços</div>
                    </div>
                    <input type="checkbox" id="show-bookmarks" {bar_checked}>
                </div>
            </div>

            <div style="text-align:center; margin-top: 10px;">
                <button class="save-btn" onclick="saveSettings()">💾 Salvar Configurações</button>
                <button class="reset-btn" onclick="resetSettings()">🔄 Restaurar Padrões</button>
            </div>

            <script>
            function encodeParams(obj){{
                const p = [];
                for (const k in obj) {{
                    p.push(encodeURIComponent(k)+'='+encodeURIComponent(obj[k]));
                }}
                return p.join('&');
            }}
            function saveSettings(){{
                const settings = {{
                    theme_color: document.getElementById('theme-color').value,
                    search_engine: document.getElementById('search-engine').value,
                    homepage: document.getElementById('homepage').value,
                    download_directory: document.getElementById('download-dir').value,
                    enable_javascript: document.getElementById('enable-js').checked,
                    show_bookmarks_bar: document.getElementById('show-bookmarks').checked
                }};
                const url = 'eirus://save-settings?' + encodeParams(settings);
                window.location.href = url;
            }}
            function resetSettings(){{
                if(confirm('Restaurar configurações padrão?')) {{
                    document.getElementById('theme-color').value = '#2D1B69';
                    document.getElementById('search-engine').value = 'https://www.google.com/search?q=';
                    document.getElementById('homepage').value = 'https://www.google.com';
                    document.getElementById('download-dir').value = '{self._safe(os.path.expanduser("~/Downloads"))}';
                    document.getElementById('enable-js').checked = true;
                    document.getElementById('show-bookmarks').checked = true;
                    alert('Configurações restauradas. Clique em Salvar para aplicar.');
                }}
            }}
            </script>
        </body></html>
        """
        return html_doc

    def _simple_welcome_page(self):
        return f"""
        <html><body style='font-family: Arial; text-align: center; padding: 50px; background:#121212; color:white;'>
            <h1>{APP_NAME}</h1>
            <p>Bem-vindo! Digite uma URL na barra de endereços para começar.</p>
        </body></html>
        """

    # -------- Aplicar engine globalmente --------
    def _apply_engine_settings_to_all(self):
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineSettings
            for i in range(self.tab_widget.count()):
                view = self.tab_widget.widget(i)
                if hasattr(view, "page"):
                    s = view.page().settings()
                    s.setAttribute(QWebEngineSettings.JavascriptEnabled, self.settings.get("enable_javascript"))
        except Exception as e:
            print(f"Falha ao aplicar configurações à engine: {e}")

    # -------- Utilidades --------
    def new_window(self):
        new_browser = FuturisticBrowser()
        new_browser.show()


# ==========================
# Execução
# ==========================

if __name__ == "__main__":
    # Tratamento global de exceções
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        error_msg = f"Erro não tratado: {exc_type.__name__}: {exc_value}"
        print(error_msg)
        try:
            if QApplication.instance():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle(f"Erro - {APP_NAME}")
                msg.setText("Ocorreu um erro inesperado:")
                msg.setDetailedText(error_msg)
                msg.exec_()
        except Exception:
            pass

    sys.excepthook = handle_exception

    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion("1.0-alpha")
        app.setOrganizationName(PROVIDER)

        # Verificar WebEngine de forma amigável
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile  # noqa
            QTimer.singleShot(0, lambda: None)
        except ImportError as e:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle(f"Erro - {APP_NAME}")
            msg.setText("PyQt5 WebEngine não encontrado!")
            msg.setInformativeText("Instale com: pip install PyQtWebEngine")
            msg.setDetailedText(str(e))
            msg.exec_()
            sys.exit(1)

        print(f"Iniciando {APP_NAME}...")
        browser = FuturisticBrowser()
        browser.show()
        print(f"{APP_NAME} iniciado com sucesso!")
        sys.exit(app.exec_())

    except Exception as e:
        error_details = f"Erro crítico na inicialização: {str(e)}\n\nDetalhes técnicos:\n{type(e).__name__}"
        print(error_details)
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle(f"Erro Crítico - {APP_NAME}")
            msg.setText("Falha na inicialização")
            msg.setInformativeText("Verifique se todas as dependências estão instaladas.")
            msg.setDetailedText(error_details)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
        except Exception:
            pass
        sys.exit(1)
