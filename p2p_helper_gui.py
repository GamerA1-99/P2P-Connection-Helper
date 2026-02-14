import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import traceback
import os
import winreg # For Windows Registry access
import threading
import json
import urllib.request
import re
from datetime import datetime
import urllib.parse
import webbrowser
import sys
import shutil # For shutil.which

# Import ctypes at the top level to ensure it's available for the AppUserModelID call.
try:
    import ctypes
except (ImportError, AttributeError):
    ctypes = None # Ensure ctypes is None if it fails to import or on non-windows

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ToolTip:
    """
    Create a tooltip for a given widget.
    """
    def __init__(self, widget, text_func):
        self.widget = widget
        self.text_func = text_func
        self.tip_window = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.on_leave)
        self.widget.bind("<ButtonPress>", self.leave) # Hide on click

    def enter(self, event=None):
        self.schedule()

    def on_leave(self, event=None):
        # This is called when the mouse leaves the widget.
        # We unschedule any pending 'showtip' and hide any visible tip.
        self.leave()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        text = self.text_func()
        if self.tip_window or not text:
            return
        # Use the widget's root coordinates directly, which is more robust
        # than relying on bbox("insert") which fails on non-text widgets.
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tip_window = tw = tk.Toplevel(self.widget)
        # Make the tooltip appear on top of other windows
        tw.wm_attributes("-topmost", True)

        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)
        # Start a recurring check to hide the tip if the mouse moves away.
        self.widget.after(100, self.check_mouse_position)

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

    def check_mouse_position(self):
        """
        Recursively checks if the mouse is still over the widget. If not,
        hides the tooltip. This is more reliable than relying on <Motion> events.
        """
        if not self.tip_window:
            return # Stop checking if the tip is already hidden

        # Get the widget's current screen coordinates and mouse position
        x, y, w, h = self.widget.winfo_rootx(), self.widget.winfo_rooty(), self.widget.winfo_width(), self.widget.winfo_height()
        mx, my = self.widget.winfo_pointerxy()

        if not (x <= mx <= x + w and y <= my <= y + h):
            self.leave()
        else:
            # If the mouse is still over, schedule another check
            self.widget.after(100, self.check_mouse_position)

class P2PHelperApp(tk.Tk):
    VERSION: str = "1.1"
    DISCLAIMER_TEXT: str = (
        "This program is intended for educational purposes, fair use, and the legal sharing of content.\n\n"
        "The use of this software and any associated P2P clients for any other purpose, including the "
        "sharing of copyrighted material without permission, is the sole responsibility of the user.\n\n"
        "The creator of this program is not responsible for the user's actions or the content they choose to share."
    )


    def __init__(self):
        super().__init__()
        self.title(f"P2P Connection Helper v{self.VERSION}")
        
        # --- Determine base path for assets (for frozen executables) ---
        self.script_dir = ""
        if getattr(sys, 'frozen', False):
            # If the application is run as a bundle/frozen executable
            self.script_dir = sys._MEIPASS
        else:
            # If running as a normal .py script
            self.script_dir = os.path.dirname(os.path.abspath(__file__))

        self.geometry("900x700")
        # --- Menu Bar ---
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Reset Settings...", command=self.reset_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Info / FAQ", command=self.show_faq_window)
        help_menu.add_command(label="About", command=self.show_about_dialog)

        self.P2P_NETWORKS = {
            "Gnutella": ["limewire", "frostwire", "wireshare", "gnutella", "xnap", "luckywire", "lemonwire", "turbowire", "cabos", "dexterwire"],
            "eDonkey/Kadmille": ["edonkey", "emule", "amule", "edonkey2000", "lphant"],
            "GnuCDNA/Gnutella2": ["gnucleus", "morpheus", "morpheus ultra", "mynapster", "phex", "gnutella2", "xolox", "kceasy", "neonapster", "bearshare"],
            "OpenNapster": ["napster", "napigator", "opennap", "filenavigator", "swaptor"],
            "WinMX": ["winmx", "winmx community patch"],
            "Unknown": []  # Fallback for manually added programs
        }

        self.EDONKEY_SERVER_LISTS = {
            "eMule Security": "http://upd.emule-security.org/server.met",
            "ShortyPower": "https://shortypower.org/server.met",
            "GitHub Backup (ShortyPower)": "https://raw.githubusercontent.com/GamerA1-99/Server.met/shortypower/server.met",
            "GitHub Backup (eMule Security)": "https://raw.githubusercontent.com/GamerA1-99/Server.met/emule-security/server.met",
        }

        self.EMULE_NODES_LISTS = {
            "eMule Security": "http://upd.emule-security.org/nodes.dat",
            "GitHub Backup (eMule Security)": "https://raw.githubusercontent.com/GamerA1-99/Server.met/emule-security/nodes.dat",
        }

        self.CUSTOM_SERVER_LISTS = {} # To store user-added server lists {network: {name: url}}
        self.installed_programs = [] # To store list of {DisplayName, ..., Network, Source}
        self.hidden_registry_keys = [] # To store registry keys of programs to ignore
        self.settings_file = "p2p_helper_settings.json" # For persistence of manually added programs
        self.selected_program = None
        self.tree_item_to_program = {} # Maps (treeview_widget, item_id) to program dict
        self.network_tabs = {} # Maps network name to its tab frame
        self.is_editing = False
        self.download_buttons = {} # Maps URL to button widget for the downloads tab
        self.faq_window = None # To hold a reference to the FAQ window
        self.icon_cache = {} # To store loaded PhotoImage objects
        self.settings = {} # To hold all loaded settings


        self.create_widgets()
        self._create_tooltips()
        self.load_settings() # Load persistent settings on startup
        self.show_bearshare_test_warning() # Show special warning if BearShare Test is found
        self.show_startup_disclaimer() # Show disclaimer after loading settings

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create a main notebook to hold the primary sections
        main_notebook = ttk.Notebook(main_frame)
        main_notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # --- Tab 1: Program Manager ---
        manager_tab = ttk.Frame(main_notebook)
        main_notebook.add(manager_tab, text="Program Manager")

        # --- Tab 2: Client & Server Downloads ---
        downloads_tab = ttk.Frame(main_notebook)
        main_notebook.add(downloads_tab, text="Client & Server Downloads")

        # Top section: Program List and Actions
        top_frame = ttk.Frame(manager_tab, padding="10")
        top_frame.pack(fill=tk.BOTH, expand=True)
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_columnconfigure(1, weight=1) # Allow details panel to expand
        top_frame.grid_rowconfigure(1, weight=1)

        # Program List Frame
        program_list_frame = ttk.LabelFrame(top_frame, text="My P2P Programs", padding="10")
        program_list_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        program_list_frame.grid_columnconfigure(0, weight=1)
        program_list_frame.grid_rowconfigure(1, weight=1)

        button_row_frame = ttk.Frame(program_list_frame)
        button_row_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        self.scan_button = ttk.Button(button_row_frame, text="Scan Registry", command=self.scan_for_programs)
        self.scan_button.pack(side=tk.LEFT, padx=(0, 5))

        self.add_manual_button = ttk.Button(button_row_frame, text="Add Manually...", command=self.add_program_manually)
        self.add_manual_button.pack(side=tk.LEFT, padx=(0, 5))

        self.edit_button = ttk.Button(button_row_frame, text="Edit", command=self.toggle_edit_mode, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=(5, 5))

        # These buttons are managed by the edit toggle and will appear in the same row
        self.save_button = ttk.Button(button_row_frame, text="Save", command=self.save_edited_program)
        self.cancel_button = ttk.Button(button_row_frame, text="Cancel", command=self.toggle_edit_mode)

        self.program_notebook = ttk.Notebook(program_list_frame)
        self.program_notebook.grid(row=1, column=0, sticky="nsew")

        # --- Program Details and Actions Frame ---
        details_frame = ttk.LabelFrame(top_frame, text="Program Details & Actions", padding="10")
        details_frame.grid(row=0, column=1, sticky="nsew")
        details_frame.grid_columnconfigure(1, weight=1)
        details_frame.grid_rowconfigure(0, weight=1) # Allow notebook to expand

        # Create a notebook for the details section to use tabs
        self.details_notebook = ttk.Notebook(details_frame)
        self.details_notebook.grid(row=0, column=0, columnspan=3, sticky="nsew")

        # -- General Tab --
        general_tab = ttk.Frame(self.details_notebook, padding=10)
        self.details_notebook.add(general_tab, text="General")
        general_tab.grid_columnconfigure(1, weight=1)

        ttk.Label(general_tab, text="Display Name:").grid(row=0, column=0, sticky="w", pady=3)
        self.display_name_var = tk.StringVar()
        self.display_name_entry = ttk.Entry(general_tab, textvariable=self.display_name_var, state="readonly")
        self.display_name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5)

        ttk.Label(general_tab, text="Executable Path:").grid(row=1, column=0, sticky="w", pady=3)
        self.exe_path_var = tk.StringVar()
        self.exe_path_entry = ttk.Entry(general_tab, textvariable=self.exe_path_var, state="readonly")
        self.exe_path_entry.grid(row=1, column=1, sticky="ew", padx=5)
        self.browse_exe_button = ttk.Button(general_tab, text="...", width=3, command=self.browse_executable_path, state="disabled")
        self.browse_exe_button.grid(row=1, column=2, sticky="e")

        ttk.Label(general_tab, text="Install Location:").grid(row=2, column=0, sticky="w", pady=3)
        self.install_location_var = tk.StringVar()
        self.install_location_entry = ttk.Entry(general_tab, textvariable=self.install_location_var, state="readonly")
        self.install_location_entry.grid(row=2, column=1, sticky="ew", padx=5)
        self.browse_install_button = ttk.Button(general_tab, text="...", width=3, command=self.browse_install_location, state="disabled")
        self.browse_install_button.grid(row=2, column=2, sticky="e")

        # -- Server List Tab --
        server_tab = ttk.Frame(self.details_notebook, padding=10)
        self.details_notebook.add(server_tab, text="Server List")
        server_tab.grid_columnconfigure(0, weight=1)
        server_tab.grid_rowconfigure(0, weight=1)

        # --- Unified Server List Management UI ---
        self.multi_url_frame = ttk.Frame(server_tab)
        self.multi_url_frame.grid(row=0, column=0, sticky='nsew')
        self.multi_url_frame.grid_columnconfigure(0, weight=1)
        self.multi_url_frame.grid_rowconfigure(0, weight=1) # Make the notebook expand
        self.multi_url_notebook = ttk.Notebook(self.multi_url_frame)
        self.multi_url_notebook.grid(row=0, column=0, sticky='nsew')
        self.multi_url_widgets = [] # To store refs to widgets in each tab

        # --- Add/Remove buttons for multi-url view ---
        self.multi_url_button_frame = ttk.Frame(self.multi_url_frame)
        self.multi_url_button_frame.grid(row=1, column=0, sticky='ew', pady=(5,0))
        self.add_multi_source_button = ttk.Button(self.multi_url_button_frame, text="Add Source", command=self.add_multi_url_source, state='disabled')
        self.add_custom_url_button = ttk.Button(self.multi_url_button_frame, text="Add Custom URL", command=self.add_custom_url, state='disabled')
        self.add_custom_url_button.pack(side='left', padx=(0,5))
        self.remove_custom_url_button = ttk.Button(self.multi_url_button_frame, text="Remove Custom URL", command=self.remove_custom_url, state='disabled')
        self.remove_custom_url_button.pack(side='left', padx=(0, 20))
        self.add_target_button = ttk.Button(self.multi_url_button_frame, text="Add Target", command=self.add_server_list_target, state='disabled')
        self.remove_target_button = ttk.Button(self.multi_url_button_frame, text="Remove Target", command=self.remove_server_list_target, state='disabled')
        self.remove_multi_source_button = ttk.Button(self.multi_url_button_frame, text="Remove Selected Source", command=self.remove_multi_url_source, state='disabled')

        # --- Common widgets for Server List tab ---
        common_server_frame = ttk.Frame(server_tab)
        common_server_frame.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        common_server_frame.grid_columnconfigure(1, weight=1) # Allow label to expand

        self.download_server_list_button = ttk.Button(common_server_frame, text="Download Sources", command=self.download_server_list, state="disabled")

        self.server_last_updated_label = ttk.Label(common_server_frame, text="Last Local Update:")
        self.server_last_updated_label.grid(row=4, column=0, sticky="w", pady=3)
        self.last_updated_var = tk.StringVar(value="N/A")
        self.server_last_updated_value = ttk.Label(common_server_frame, textvariable=self.last_updated_var, font=("Segoe UI", 9, "italic"), foreground="gray")
        self.server_last_updated_value.grid(row=4, column=1, sticky="w", padx=5, pady=3)

        self.server_remote_updated_label = ttk.Label(common_server_frame, text="Server Update:")
        self.server_remote_updated_label.grid(row=5, column=0, sticky="w", pady=3)
        self.remote_last_updated_var = tk.StringVar(value="N/A")
        self.server_remote_updated_value = ttk.Label(common_server_frame, textvariable=self.remote_last_updated_var, font=("Segoe UI", 9, "italic"), foreground="gray")
        self.server_remote_updated_value.grid(row=5, column=1, sticky="w", padx=5, pady=3)
        ToolTip(self.server_remote_updated_value, lambda: "Last modification date of the file on the remote server. 'N/A' may mean the server doesn't provide this info.")


        # --- Action Buttons ---
        # Main action buttons are at the bottom of the General tab
        action_buttons_frame = ttk.Frame(general_tab)
        action_buttons_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(20, 0))
        self.launch_button = ttk.Button(action_buttons_frame, text="Launch Program", command=self.launch_selected_program, state=tk.DISABLED)
        self.launch_button.pack(side=tk.LEFT, padx=(0, 5))

        self.open_config_button = ttk.Button(action_buttons_frame, text="Open Config Folder", command=self.open_config_folder, state=tk.DISABLED)
        self.open_config_button.pack(side=tk.LEFT, padx=(0, 5))

        self.remove_program_button = ttk.Button(action_buttons_frame, text="Remove Program", command=self.remove_program, state=tk.DISABLED)
        self.remove_program_button.pack(side=tk.RIGHT)

        # --- Kademlia (Nodes) section, shown dynamically in Server List tab for eMule ---
        self.nodes_frame = ttk.LabelFrame(server_tab, text="Kademlia (nodes.dat)", padding=10)
        # This frame is gridded dynamically in display_details_panel
        self.nodes_frame.grid_columnconfigure(1, weight=1)

        self.nodes_url_label = ttk.Label(self.nodes_frame, text="Nodes List URL:")
        self.nodes_url_label.grid(row=0, column=0, sticky="w", pady=3)
        self.nodes_list_url_var = tk.StringVar()
        self.nodes_list_url_var.trace_add("write", self.on_nodes_list_url_change)
        self.nodes_list_url_entry = ttk.Entry(self.nodes_frame, textvariable=self.nodes_list_url_var, state="disabled")
        self.nodes_list_url_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.nodes_list_url_combo = ttk.Combobox(self.nodes_frame, textvariable=self.nodes_list_url_var, state="disabled")
        self.nodes_list_url_combo.grid(row=0, column=1, sticky="ew", padx=5)
        self.nodes_list_url_combo.bind("<<ComboboxSelected>>", self.on_nodes_list_select)
        self.test_nodes_url_button = ttk.Button(self.nodes_frame, text="Test", command=lambda: self.test_url(self.nodes_list_url_var, is_nodes_dat=True), state="disabled")
        self.test_nodes_url_button.grid(row=0, column=2, sticky="e")
        self.download_nodes_list_button = ttk.Button(self.nodes_frame, text="Download", command=self.download_nodes_list, state="disabled")
        self.download_nodes_list_button.grid(row=0, column=3, sticky="e")

        self.nodes_target_label = ttk.Label(self.nodes_frame, text="Nodes List Target:")
        self.nodes_target_label.grid(row=1, column=0, sticky="w", pady=3)
        self.nodes_list_target_var = tk.StringVar()
        self.nodes_list_target_var.trace_add("write", self.on_nodes_list_url_change)
        self.nodes_list_target_entry = ttk.Entry(self.nodes_frame, textvariable=self.nodes_list_target_var, state="disabled")
        self.nodes_list_target_entry.grid(row=1, column=1, sticky="ew", padx=5)
        self.browse_nodes_target_button = ttk.Button(self.nodes_frame, text="...", width=3, command=lambda: self.browse_generic_target(self.nodes_list_target_var, "nodes.dat"), state="disabled")
        self.browse_nodes_target_button.grid(row=1, column=3, sticky="e")

        self.nodes_last_updated_label = ttk.Label(self.nodes_frame, text="Last Local Update:")
        self.nodes_last_updated_label.grid(row=2, column=0, sticky="w", pady=3)
        self.nodes_last_updated_var = tk.StringVar(value="N/A")
        self.nodes_last_updated_value = ttk.Label(self.nodes_frame, textvariable=self.nodes_last_updated_var, font=("Segoe UI", 9, "italic"), foreground="gray")
        self.nodes_last_updated_value.grid(row=2, column=1, sticky="w", padx=5, pady=3)

        self.nodes_remote_updated_label = ttk.Label(self.nodes_frame, text="Server Update:")
        self.nodes_remote_updated_label.grid(row=3, column=0, sticky="w", pady=3)
        self.nodes_remote_last_updated_var = tk.StringVar(value="N/A")
        self.nodes_remote_updated_value = ttk.Label(self.nodes_frame, textvariable=self.nodes_remote_last_updated_var, font=("Segoe UI", 9, "italic"), foreground="gray")
        self.nodes_remote_updated_value.grid(row=3, column=1, sticky="w", padx=5, pady=3)
        ToolTip(self.nodes_remote_updated_value, lambda: "Last modification date of the file on the remote server. 'N/A' may mean the server doesn't provide this info.")

        # --- WinMX Patch section, shown dynamically in Server List tab ---
        self.winmx_patch_frame = ttk.LabelFrame(server_tab, text="WinMX Connection Patch (oledlg.dll)", padding=10)
        # This frame is gridded dynamically in display_details_panel
        self.winmx_patch_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(self.winmx_patch_frame, text="Patch URL:").grid(row=0, column=0, sticky="w", pady=3)
        self.winmx_patch_url_var = tk.StringVar()
        self.winmx_patch_url_var.trace_add("write", self.on_winmx_patch_change)
        self.winmx_patch_url_entry = ttk.Entry(self.winmx_patch_frame, textvariable=self.winmx_patch_url_var, state="disabled")
        self.winmx_patch_url_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.test_winmx_patch_url_button = ttk.Button(self.winmx_patch_frame, text="Test", command=lambda: self.test_url(self.winmx_patch_url_var), state="disabled")
        self.test_winmx_patch_url_button.grid(row=0, column=2, sticky="e")
        self.download_winmx_patch_button = ttk.Button(self.winmx_patch_frame, text="Download", command=self.download_winmx_patch, state="disabled")
        self.download_winmx_patch_button.grid(row=0, column=3, sticky="e")

        ttk.Label(self.winmx_patch_frame, text="Patch Target:").grid(row=1, column=0, sticky="w", pady=3)
        self.winmx_patch_target_var = tk.StringVar()
        self.winmx_patch_target_var.trace_add("write", self.on_winmx_patch_change)
        self.winmx_patch_target_entry = ttk.Entry(self.winmx_patch_frame, textvariable=self.winmx_patch_target_var, state="disabled")
        self.winmx_patch_target_entry.grid(row=1, column=1, sticky="ew", padx=5)
        self.browse_winmx_patch_target_button = ttk.Button(self.winmx_patch_frame, text="...", width=3, command=lambda: self.browse_generic_target(self.winmx_patch_target_var, "OLEDLG.DLL"), state="disabled")
        self.browse_winmx_patch_target_button.grid(row=1, column=3, sticky="e")

        self.winmx_patch_last_updated_label = ttk.Label(self.winmx_patch_frame, text="Last Local Update:")
        self.winmx_patch_last_updated_label.grid(row=2, column=0, sticky="w", pady=3)
        self.winmx_patch_last_updated_var = tk.StringVar(value="N/A")
        self.winmx_patch_last_updated_value = ttk.Label(self.winmx_patch_frame, textvariable=self.winmx_patch_last_updated_var, font=("Segoe UI", 9, "italic"), foreground="gray")
        self.winmx_patch_last_updated_value.grid(row=2, column=1, sticky="w", padx=5, pady=3)

        self.winmx_remote_updated_label = ttk.Label(self.winmx_patch_frame, text="Server Update:")
        self.winmx_remote_updated_label.grid(row=3, column=0, sticky="w", pady=3)
        self.winmx_remote_last_updated_var = tk.StringVar(value="N/A")
        self.winmx_remote_updated_value = ttk.Label(self.winmx_patch_frame, textvariable=self.winmx_remote_last_updated_var, font=("Segoe UI", 9, "italic"), foreground="gray")
        self.winmx_remote_updated_value.grid(row=3, column=1, sticky="w", padx=5, pady=3)
        ToolTip(self.winmx_remote_updated_value, lambda: "Last modification date of the file on the remote server. 'N/A' may mean the server doesn't provide this info.")

        # Log output
        log_frame = ttk.LabelFrame(manager_tab, text="Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10)
        # Make the widget read-only by intercepting key presses, but keep it
        # in a 'normal' state so that text can be selected and copied.
        self.log_text.bind("<KeyPress>", lambda e: "break")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # --- Log Context Menu ---
        self.log_context_menu = tk.Menu(self.log_text, tearoff=0)
        self.log_context_menu.add_command(label="Copy", command=self.copy_log_text)
        self.log_context_menu.add_command(label="Copy All", command=self.copy_all_log_text)
        self.log_context_menu.add_separator()
        self.log_context_menu.add_command(label="Clear Log", command=self.clear_log)
        self.log_text.bind("<Button-3>", self.show_log_context_menu)

        # --- Populate the Client Downloads Tab ---
        self._create_downloads_tab_widgets(downloads_tab)

    CLIENT_DOWNLOADS = {
        "BearShare": "https://drive.google.com/drive/folders/1EWyiP_d9drmVTv5vMQuj2t_Kn6muhebv?usp=drive_link",
        "Cabos": "https://drive.google.com/drive/folders/1W0w4437xqS9E-ePTVM-xnJGlL_sOzof_?usp=sharing",
        "DexterWire": "https://drive.google.com/drive/folders/1JkUdMU5UdRYYxwo8TpBtBOEmCycyritz?usp=sharing",
            "FileNavigator": "https://drive.google.com/drive/folders/1jJPC8ycS-9Lw6JkMTNLacWXY3BIUFLG-?usp=drive_link",
        "FrostWire": "https://drive.google.com/drive/folders/1U9n6Qkx49ifIViFa8t7VXzu7DV7597e6?usp=drive_link",
        "LimeWire": "https://drive.google.com/drive/folders/14PE3oD6w8eOjInfMd4CH3ZLVzI975CtS?usp=sharing",
        "WireShare": "https://drive.google.com/drive/folders/1gJLahU-qczlV9lOPy7IAOUPEZrtcoY-Z?usp=drive_link",
        "XNap": "https://drive.google.com/drive/folders/1DBThKI6V2ifgxcHP0uD2z1bObD_YAKp1?usp=drive_link",
        "WinMX": "https://drive.google.com/drive/folders/1_XU09g1pMfEU-j5maGtDdnwWnBOutIo-?usp=sharing",
        "KCeasy": "https://drive.google.com/drive/folders/1th_HLwnkTyd8_cUjIKyaAANBJ_XgXnV8?usp=drive_link",
        "SlavaNap Server": "https://drive.google.com/drive/folders/1UyVZbQcFhBbKlZ2gghzsIUMjNrA4rb7O?usp=sharing",
        "phpgnucacheii server": "https://drive.google.com/drive/folders/1_hqw2PIQkxskvI_pZ39em9VbcdDJb6yE?usp=sharing",
        "Phex": "https://drive.google.com/drive/folders/1rVLm7spxVXVnyKIDmZfsU3P2mJaLT_MW?usp=sharing",
        "OpenNap server": "https://drive.google.com/drive/folders/1GjtY9xokWWShS5OwK-RntMj5vc6ljJi2?usp=sharing",
        "LemonWire": "https://drive.google.com/drive/folders/1fWoAKCfSLIJoNrAILh7UokXvMKO5E1-4?usp=drive_link",
        "LuckyWire": "https://drive.google.com/drive/folders/1boGgSO685-OAv2V0vgrxcelgfr2qQPRM?usp=drive_link",
        "Napster": "https://drive.google.com/drive/folders/1m-kOzQHRrlFCcZa5E_mAsp_RXuZ4-5yI?usp=sharing",
        "Napigator": "https://drive.google.com/drive/folders/1LQVoKYTDFuBpCpBriVdDc9RV_3D3rQ6v?usp=sharing",
        "MyNapster": "https://drive.google.com/drive/folders/1qJPcZtPVXa-818uyBlIkx0EekUDv3-MA?usp=sharing",
        "Morpheus": "https://drive.google.com/drive/folders/1ZWaIePi1ilXLmfS4c0wpVWKpYjZO7mhP?usp=sharing",
        "GWebCache Server": "https://drive.google.com/drive/folders/1H6GAcdZz4ysA8xd9TdhBe0VY9kS7Ldyv?usp=sharing",
        "NeoNapster": "https://drive.google.com/drive/folders/1gXRspQgy1t8465fVG0fWKDNXV9DDIfRS?usp=drive_link",
        "GWC Server": "https://drive.google.com/drive/folders/162UOw_by8ws4AG5YfnWoUJ40KbUJbvhG?usp=sharing",
        "Lphant": "https://drive.google.com/drive/folders/1j7cEcSybibFJRoI5-Cp0egv-lmYDr_1d?usp=sharing",
        "Gnucleus": "https://drive.google.com/drive/folders/1cWFLVg2hvhNu73CWa7FPVn9VoXlDRv6e?usp=sharing",
        "Red Flags Server": "https://drive.google.com/drive/folders/1SxT1Vhtxg6zEkP9jbwtRF5lXPDMLoFtu?usp=sharing",
        "XoloX": "https://drive.google.com/drive/folders/1NrrdEC4fdyGe2LI4SQqUfJ8GBuj4n-_K?usp=drive_link",
        "eMule": "https://drive.google.com/drive/folders/1gfoasXE-41NYXKaGz8Wa1m8a323eI5JF?usp=sharing",
        "Swaptor": "https://drive.google.com/drive/folders/1_4eX_ElQUrNdRtFBBScOCPDhTs8loc-L?usp=drive_link",
        "TurboWire": "https://drive.google.com/drive/folders/15DMXkgmGUMLib-XZSUG340YRXlxUlxX9?usp=drive_link",
        "eDonkey 2000": "https://drive.google.com/drive/folders/1_sEPQOkwcm12J0SEj4qZXeuh3sWvDuzQ?usp=sharing",
        "Cachechu Server": "https://drive.google.com/drive/folders/1WbQpq8ifFu-1Z7usFcw6UaBEap8jrWCO?usp=sharing",
        "Beacon2 Server": "https://drive.google.com/drive/folders/1FmnvGTSgbIBQuiz1U_g6sApkygeJqs3a?usp=sharing",
        "Beacon Server": "https://drive.google.com/drive/folders/1WNcf5pgI4Nvn231jvLpZ-JthciUwJf7J?usp=sharing",
        "Beacon1 Server": "https://drive.google.com/drive/folders/11Yv1PN3ZyT0GwMyEFTaj9C1OE15XFt0I?usp=sharing",
    }

    def _create_downloads_tab_widgets(self, parent_tab):
        """Populates the Client & Server Downloads tab with categorized panels."""
        frame = ttk.Frame(parent_tab, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
    
        # Top frame for description and test button
        top_bar_frame = ttk.Frame(frame)
        top_bar_frame.pack(fill=tk.X, pady=(0, 20))

        description_text = ("This section provides links to download various P2P client installers and server applications. "
                            "Click a button to open a web page to download the files. Use the 'Test All Links' button to check for broken links.")
        ttk.Label(top_bar_frame, text=description_text, wraplength=600, justify=tk.LEFT).pack(side=tk.LEFT, anchor='w')

        self.test_downloads_button = ttk.Button(top_bar_frame, text="Test All Links", command=self.test_all_download_links)
        self.test_downloads_button.pack(side=tk.RIGHT, padx=10, pady=10)

        # Progress bar for link testing, initially hidden
        self.download_test_progress = ttk.Progressbar(frame, orient='horizontal', mode='determinate')
        # This progress bar will be packed/unpacked by the test function.

        # Define a list of names that are servers and should not have icons
        server_names = [
            "SlavaNap Server", "phpgnucacheii server", "OpenNap server",
            "GWebCache Server", "GWC Server", "Red Flags Server", "Cachechu Server",
            "Beacon2 Server", "Beacon1 Server", "Beacon Server"
        ]

        # Separate clients from servers
        clients = {name: url for name, url in self.CLIENT_DOWNLOADS.items() if name not in server_names}
        servers = {name: url for name, url in self.CLIENT_DOWNLOADS.items() if name in server_names}

        # Special mapping for client names that don't match their icon filename
        icon_map = {
            "eDonkey 2000": "eDonkey.ico",
            "Lphant": "lphant.ico",
            "LemonWire": "lemonwire.ico",
            "TurboWire": "turbowire.ico",
            "LuckyWire": "luckywire.ico"
        }

        # Create a main frame to hold the two panels
        panels_frame = ttk.Frame(frame)
        panels_frame.pack(fill=tk.BOTH, expand=True)
        panels_frame.columnconfigure(0, weight=1)
        panels_frame.columnconfigure(1, weight=1)

        # --- Clients Panel ---
        client_panel = ttk.LabelFrame(panels_frame, text="Clients", padding="10")
        client_panel.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        client_panel.columnconfigure(0, weight=1)
        client_panel.columnconfigure(1, weight=1)

        row, col = 0, 0
        for client_name, url in sorted(clients.items()):
            icon = None
            icon_filename = icon_map.get(client_name, f"{client_name.replace(' ', '')}.ico")
            icon = self._load_icon(icon_filename) # Pass only the filename
            button = ttk.Button(client_panel, text=client_name, image=icon, compound=tk.LEFT, command=lambda u=url: self._open_download_url(u))
            self.download_buttons[url] = button # Store the button
            button.grid(row=row, column=col, sticky='ew', padx=5, pady=5)
            col += 1
            if col >= 2:
                col = 0
                row += 1

        # --- Servers Panel ---
        server_panel = ttk.LabelFrame(panels_frame, text="Servers", padding="10")
        server_panel.grid(row=0, column=1, sticky='nsew')
        server_panel.columnconfigure(0, weight=1)

        for i, (server_name, url) in enumerate(sorted(servers.items())):
            # Servers are in a single column without icons
            button = ttk.Button(server_panel, text=server_name, command=lambda u=url: self._open_download_url(u))
            self.download_buttons[url] = button # Store the button
            button.grid(row=i, column=0, sticky='ew', padx=5, pady=5)

    def _open_download_url(self, url):
        """Opens the specified URL in the default web browser."""
        self.log_message(f"Opening URL in browser: {url}")
        webbrowser.open_new_tab(url)

    def test_all_download_links(self):
        """Starts a thread to test all download links in the Downloads tab."""
        self.log_message("Starting to test all client/server download links...")
        # Reset button states before starting
        for button in self.download_buttons.values():
            button.config(state=tk.NORMAL)

        self.test_downloads_button.config(state=tk.DISABLED, text="Testing...")

        # Show and configure the progress bar
        total_links = len(self.CLIENT_DOWNLOADS)
        self.download_test_progress.config(maximum=total_links, value=0)
        self.download_test_progress.pack(fill=tk.X, padx=20, pady=(0, 10), before=self.download_buttons[next(iter(self.download_buttons))].master.master)

        threading.Thread(target=self._perform_download_links_test, args=(total_links,), daemon=True).start()

    def _perform_download_links_test(self, total_links):
        """Worker thread to test each download link."""
        dead_links = []
        for i, url in enumerate(self.CLIENT_DOWNLOADS.values()):
            try:
                # Use a HEAD request to check for existence without downloading the content
                req = urllib.request.Request(url, method='HEAD')
                # Google Drive links often redirect, so we need to handle that.
                # A simple HEAD request might fail, but urlopen will follow redirects.
                with urllib.request.urlopen(req, timeout=10) as response:
                    if not (200 <= response.getcode() < 400): # 2xx is success, 3xx is redirect (also good)
                        dead_links.append(url)
            except Exception:
                dead_links.append(url)
            # Schedule a progress bar update on the main thread
            self.after(0, self.download_test_progress.config, {'value': i + 1})

        self.after(0, self._update_download_buttons_state, dead_links)

    def _update_download_buttons_state(self, dead_links):
        """Updates the state of download buttons based on the test results."""
        for url, button in self.download_buttons.items():
            if url in dead_links:
                button.config(state=tk.DISABLED)
        self.log_message(f"Link test complete. Found {len(dead_links)} unresponsive link(s).")
        self.test_downloads_button.config(state=tk.NORMAL, text="Test All Links")
        self.download_test_progress.pack_forget() # Hide the progress bar
        messagebox.showinfo("Test Complete", f"Finished testing all download links.\n\nUnresponsive links have been greyed out.")

    def log_message(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def show_log_context_menu(self, event):
        """Displays the log's right-click context menu."""
        # Check if there is any text in the log widget at all.
        # The widget always contains a newline character, so we check if the length is more than 1.
        has_text = self.log_text.get(1.0, tk.END) and len(self.log_text.get(1.0, tk.END)) > 1

        # Disable 'Copy' if no text is selected
        if self.log_text.tag_ranges("sel"):
            self.log_context_menu.entryconfig("Copy", state=tk.NORMAL)
        else:
            self.log_context_menu.entryconfig("Copy", state=tk.DISABLED)

        # Disable 'Copy All' and 'Clear Log' if there is no text
        if has_text:
            self.log_context_menu.entryconfig("Copy All", state=tk.NORMAL)
            self.log_context_menu.entryconfig("Clear Log", state=tk.NORMAL)
        else:
            self.log_context_menu.entryconfig("Copy All", state=tk.DISABLED)
            self.log_context_menu.entryconfig("Clear Log", state=tk.DISABLED)

        self.log_context_menu.post(event.x_root, event.y_root)

    def copy_log_text(self):
        """Handles the 'Copy' action from the log context menu."""
        self.log_text.event_generate("<<Copy>>")

    def copy_all_log_text(self):
        """Copies all text from the log widget to the clipboard."""
        self.clipboard_clear()
        self.clipboard_append(self.log_text.get(1.0, tk.END))

    def clear_log(self):
        """Clears all text from the log widget."""
        self.log_text.delete(1.0, tk.END)

    def _create_tooltips(self):
        """Create tooltips for widgets that might have truncated text."""
        # Tooltip for the program name in the details panel
        # General Tab
        ToolTip(self.display_name_entry, lambda: self.display_name_var.get())
        ToolTip(self.exe_path_entry, lambda: self.exe_path_var.get())
        ToolTip(self.install_location_entry, lambda: self.install_location_var.get())
        ToolTip(self.launch_button, lambda: "Launch the selected program")
        ToolTip(self.open_config_button, lambda: "Open the installation folder for the selected program")
        ToolTip(self.remove_program_button, lambda: "Remove the selected program from this list (does not uninstall)")

        # Program List Buttons
        ToolTip(self.scan_button, lambda: "Scan the Windows Registry for installed P2P programs")
        ToolTip(self.add_manual_button, lambda: "Add a program to the list manually")
        ToolTip(self.edit_button, lambda: "Edit the details of the selected program")
        ToolTip(self.save_button, lambda: "Save changes to the program details")
        ToolTip(self.cancel_button, lambda: "Cancel editing and discard changes")

        # Server List Tab
        ToolTip(self.download_server_list_button, lambda: "Download server lists from all configured sources to their target paths")
        ToolTip(self.add_target_button, lambda: "Add a new target file path for the selected source")
        ToolTip(self.remove_target_button, lambda: "Remove the selected target file path")
        ToolTip(self.add_multi_source_button, lambda: "Add a new server list source (URL or local file)")
        ToolTip(self.remove_multi_source_button, lambda: "Remove the currently selected server list source")
        ToolTip(self.add_custom_url_button, lambda: "Add a new custom server list URL to the dropdown for this network")
        ToolTip(self.remove_custom_url_button, lambda: "Remove a custom server list URL from the dropdown")

        # Kademlia (nodes.dat) section
        ToolTip(self.nodes_list_url_combo, lambda: self.nodes_list_url_var.get())
        ToolTip(self.nodes_list_target_entry, lambda: self.nodes_list_target_var.get())
        ToolTip(self.test_nodes_url_button, lambda: "Test if the nodes.dat URL is reachable")
        ToolTip(self.download_nodes_list_button, lambda: "Download the nodes.dat file to the target path")
        ToolTip(self.browse_nodes_target_button, lambda: "Browse for the nodes.dat target file")

        # WinMX Patch section
        ToolTip(self.winmx_patch_url_entry, lambda: self.winmx_patch_url_var.get())
        ToolTip(self.winmx_patch_target_entry, lambda: self.winmx_patch_target_var.get())
        ToolTip(self.test_winmx_patch_url_button, lambda: "Test if the patch URL is reachable")
        ToolTip(self.download_winmx_patch_button, lambda: "Download the patch file to the target path")
        ToolTip(self.browse_winmx_patch_target_button, lambda: "Browse for the patch target file")

        # Downloads Tab
        ToolTip(self.test_downloads_button, lambda: "Check all download links and disable any that are unresponsive")


    def _get_custom_lists_for_network(self, network):
        """Safely gets the custom server lists for a given network."""
        if network not in self.CUSTOM_SERVER_LISTS:
            self.CUSTOM_SERVER_LISTS[network] = {}
        return self.CUSTOM_SERVER_LISTS[network]
    def load_settings(self):
        """Loads program data from a JSON file."""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
                    self.hidden_registry_keys = self.settings.get("hidden_registry_keys", [])
                    self.CUSTOM_SERVER_LISTS = self.settings.get("custom_server_lists", {})
                    self.installed_programs = self.settings.get("programs", [])
                    self._update_program_list_ui()
                    self.log_message("Loaded programs from settings file.")
            except json.JSONDecodeError as e:
                self.log_message(f"Error decoding settings file (p2p_helper_settings.json): {e}")
            except Exception as e:
                self.log_message(f"An unexpected error occurred while loading settings: {e}")

    def save_settings(self):
        """Saves program data to a JSON file."""
        try:
            # Save all current programs to the settings file.
            # Update the main settings dictionary before saving
            self.settings["programs"] = self.installed_programs
            self.settings["hidden_registry_keys"] = self.hidden_registry_keys
            self.settings["custom_server_lists"] = self.CUSTOM_SERVER_LISTS

            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)

            self.log_message("Settings saved.")
        except Exception as e:
            self.log_message(f"Error saving settings: {e}")

    def scan_for_programs(self):
        self.log_message("Scanning for installed P2P programs...")
        
        # Clear previous registry-detected programs, keep manual ones
        self.installed_programs = [p for p in self.installed_programs if p.get("Source") == "Manual"]

        threading.Thread(target=self._scan_registry_for_programs, daemon=True).start()

    def _scan_registry_for_programs(self):
        uninstall_keys = [
            winreg.HKEY_LOCAL_MACHINE,
            winreg.HKEY_CURRENT_USER
        ]
        subkeys = [
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall" # For 32-bit apps on 64-bit Windows
        ]

        programs_found = []

        for hkey in uninstall_keys:
            for subkey_path in subkeys:
                try:
                    key = winreg.OpenKey(hkey, subkey_path, 0, winreg.KEY_READ)
                    i = 0
                    while True:
                        try:
                            name = winreg.EnumKey(key, i)

                            # Skip this program if it's in the hidden list
                            if name in self.hidden_registry_keys:
                                i += 1
                                continue
                            subkey = winreg.OpenKey(key, name)
                            display_name = None
                            install_location = None
                            executable_path = None # Initialize here
                            
                            # Try to get DisplayName, InstallLocation, and DisplayIcon
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            except FileNotFoundError:
                                pass

                            # Exclude specific programs that don't need this tool
                            if display_name and "gtk-gnutella" in display_name.lower():
                                i += 1
                                continue
                            try:
                                install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            except FileNotFoundError:
                                pass
                            try:
                                # DisplayIcon often contains the full path to the executable.
                                # It might have a comma and a number for the icon index, so we strip that.
                                display_icon_path = winreg.QueryValueEx(subkey, "DisplayIcon")[0]
                                parsed_path = display_icon_path.split(',')[0].strip('"')
                                if os.path.exists(parsed_path) and parsed_path.lower().endswith(('.exe', '.jar')):
                                    executable_path = parsed_path # This is our best guess for the executable
                                    # If InstallLocation is missing, derive it from the executable path
                                    if not install_location:
                                        install_location = os.path.dirname(executable_path)
                            except FileNotFoundError:
                                pass

                            network_type, matched_keyword = None, None
                            if display_name:
                                for network, keywords in self.P2P_NETWORKS.items():
                                    for keyword in keywords:
                                        if keyword in display_name.lower():
                                            network_type = network
                                            matched_keyword = keyword
                                            break
                                    if network_type:
                                        network_type = network
                                        break
                            
                            if network_type:
                                    program_info = {
                                        "DisplayName": display_name,
                                        "InstallLocation": install_location,
                                        "ExecutablePath": executable_path,
                                        "ServerListURL": "", # Placeholder for user input
                                        "ServerListTargetPaths": {}, # Placeholder for user input
                                        "Source": "Registry",
                                        "Network": network_type,
                                        "NodesListURL": "",
                                        "RegistryKey": name, # Store the unique registry key name
                                        "NodesLastUpdated": "N/A",
                                        "MatchedKeyword": matched_keyword,
                                        "NodesListTargetPath": "",
                                    }
                                    self._prefill_opennap_info(program_info)
                                    self._prefill_gnutella_info(program_info)
                                    self._prefill_edonkey_info(program_info)
                                    self._prefill_gnucdna_info(program_info, client_type=matched_keyword)
                                    self._prefill_winmx_info(program_info)
                                    programs_found.append(program_info)

                            winreg.CloseKey(subkey)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    self.after(0, self.log_message, f"Error accessing registry: {e}")

        # Get a set of registry keys for programs that have been manually edited.
        # This prevents re-adding a program that the user has customized.
        manual_registry_keys = {p.get("RegistryKey") for p in self.installed_programs if p.get("Source") == "Manual" and p.get("RegistryKey")}

        # Start with the existing manual/edited programs.
        final_programs = [p for p in self.installed_programs if p.get("Source") == "Manual"]

        for p in programs_found:
            if p.get("RegistryKey") not in manual_registry_keys:
                final_programs.append(p)

        self.installed_programs = sorted(final_programs, key=lambda x: x["DisplayName"].lower())
        self.after(0, self._update_program_list_ui)
        self.after(0, self.log_message, f"Scan complete. Found {len(programs_found)} new programs.")
        # After a scan, check again for the BearShare Test warning in case it was just found.
        self.after(0, self.show_bearshare_test_warning)
        self.after(0, self.save_settings) # Save the updated list

    def _load_icon(self, icon_path, size=(16, 16)):
        """Loads an icon from a path, resizes it, and caches it."""
        cache_key = os.path.basename(icon_path)
        if not PIL_AVAILABLE or not cache_key:
            return None
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]
        
        resolved_path = os.path.join(self.script_dir, cache_key)
        try: # Check for existence before trying to open
            img = Image.open(resolved_path)
            img = img.resize(size, Image.Resampling.LANCZOS)
            photo_img = ImageTk.PhotoImage(img)
            self.icon_cache[cache_key] = photo_img # Cache it
            return photo_img
        except (FileNotFoundError, Exception) as e:
            # Don't log file not found, as we try multiple paths.
            if not isinstance(e, FileNotFoundError):
                self.log_message(f"Warning: Could not load icon '{resolved_path}': {e}")
            return None

    def _update_program_list_ui(self):
        # Clear old data
        self.tree_item_to_program.clear()
        for tab in self.program_notebook.tabs():
            self.program_notebook.forget(tab)
        self.network_tabs.clear()
        
        # Group programs by network
        programs_by_network = {}
        for program in self.installed_programs:
            network = program.get("Network", "Unknown")
            if network not in programs_by_network:
                programs_by_network[network] = []
            programs_by_network[network].append(program)

            # Handle programs that should appear in multiple network tabs
            for also_in_network in program.get("AlsoInNetworks", []):
                if also_in_network not in programs_by_network:
                    programs_by_network[also_in_network] = []
                programs_by_network[also_in_network].append(program)

        # Define the network icon map for both tabs and treeview fallbacks
        network_icon_map = {
            "eDonkey/Kadmille": ["eDonkey.ico", "eDonkeyKadmille.ico"],
            "Gnutella": ["gnutella.ico"],
            "GnuCDNA/Gnutella2": ["gnucleus.ico", "gnutella2.ico"], # Will be combined if both exist
            "OpenNapster": ["opennapster.ico", "opennap.ico"],
            "WinMX": ["WinMX.ico"],
        } 

        # This map was missing, causing a NameError. It's for clients whose
        # display name doesn't match their icon file name.
        icon_map = {
            "eDonkey 2000": "eDonkey.ico",
            "Lphant": "lphant.ico",
            "LemonWire": "lemonwire.ico",
            "TurboWire": "turbowire.ico"
        }
        # Create a tab for each network
        for network in sorted(programs_by_network.keys()):
            # Create tab frame
            tab_frame = ttk.Frame(self.program_notebook, padding=5)
            tab_frame.grid_columnconfigure(0, weight=1)
            tab_frame.grid_rowconfigure(0, weight=1) # This was missing

            # --- Find and apply icon(s) for the tab label ---
            tab_icon = None
            possible_icons = network_icon_map.get(network, [])
            found_icons = [os.path.join(self.script_dir, f) for f in possible_icons if os.path.exists(os.path.join(self.script_dir, f))]

            if len(found_icons) > 1 and PIL_AVAILABLE: # Logic for combining multiple icons
                # If multiple icons are found (e.g., for GnuCDNA/Gnutella2), create a composite image.
                try:
                    # Use a unique cache key for the combined image
                    cache_key = "+".join(found_icons)
                    if cache_key in self.icon_cache:
                        tab_icon = self.icon_cache[cache_key]
                    else:
                        images = [Image.open(f).resize((16, 16), Image.Resampling.LANCZOS) for f in found_icons] # f is already a full path
                        total_width = sum(img.width for img in images)
                        max_height = max(img.height for img in images)
                        
                        composite_img = Image.new('RGBA', (total_width, max_height))
                        x_offset = 0
                        for img in images:
                            composite_img.paste(img, (x_offset, 0), img if img.mode == 'RGBA' else None)
                            x_offset += img.width
                        
                        tab_icon = ImageTk.PhotoImage(composite_img)
                        self.icon_cache[cache_key] = tab_icon # Cache the new composite icon
                except Exception as e:
                    self.log_message(f"Warning: Could not create composite icon for tab '{network}': {e}")
                    # Fallback to the first available icon
                    if found_icons:
                        tab_icon = self._load_icon(os.path.basename(found_icons[0]))
            elif len(found_icons) == 1: # Logic for a single icon
                # If only one icon is found, load it normally.
                tab_icon = self._load_icon(os.path.basename(found_icons[0]))

            if tab_icon:
                self.program_notebook.add(tab_frame, text=network, image=tab_icon, compound=tk.LEFT)
            else:
                self.program_notebook.add(tab_frame, text=network)

            self.network_tabs[network] = tab_frame

            # Create Treeview for the tab
            tree = ttk.Treeview(tab_frame, selectmode="browse", show="tree", columns=())
            tree.grid(row=0, column=0, sticky="nsew")
            tree.bind("<<TreeviewSelect>>", self.on_program_selection)

            # Add scrollbar to the treeview
            # Add a tooltip handler for the treeview
            scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=tree.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            tree.configure(yscrollcommand=scrollbar.set)

            # Populate the treeview
            for program in sorted(programs_by_network[network], key=lambda p: p["DisplayName"]):
                icon = None
                display_name = program["DisplayName"]
                
                # --- Icon Loading Logic ---
                # 1. Check for an explicit IconPath in the program data (highest priority).
                explicit_icon_filename = program.get("IconPath")
                if explicit_icon_filename:
                    icon = self._load_icon(explicit_icon_filename)

                # 1b. Check the download icon map as a fallback
                if not icon:
                    icon_filename = icon_map.get(display_name)
                    if icon_filename:
                        icon = self._load_icon(icon_filename)
                
                # 2. If no icon, check for a local icon file based on the program's exact DisplayName.
                #    e.g., "eMule v0.50a" -> "eMule v0.50a.ico"
                if not icon and display_name:
                    local_icon_filename = f"{display_name}.ico"
                    icon = self._load_icon(local_icon_filename)

                # 3. If still no icon, check for a local icon file based on the program's matched keyword.
                #    e.g., MatchedKeyword "emule" -> "emule.ico"
                if not icon:
                    keyword = program.get("MatchedKeyword")
                    if keyword:
                        icon = self._load_icon(f"{keyword}.ico")
                        if not icon:
                            # Also check for the capitalized version as a fallback
                            icon = self._load_icon(f"{keyword.capitalize()}.ico")

                # 4. As a final fallback, check for an icon matching the network name.
                #    e.g., "eDonkey/Kadmille" -> "eDonkeyKadmille.ico"
                if not icon:
                    network = program.get("Network")
                    if network:
                        possible_icons = network_icon_map.get(network, [])
                        for icon_filename in possible_icons:
                            icon = self._load_icon(icon_filename)
                            if icon:
                                break # Stop after finding the first valid icon

                # Truncate the display name for the treeview to prevent layout issues
                max_len = 50
                truncated_name = (display_name[:max_len] + '...') if len(display_name) > max_len else display_name

                # Only add the image argument if the icon was successfully loaded.
                # Passing image=None causes a TclError.
                if icon:
                    item_id = tree.insert("", "end", text=truncated_name, image=icon, values=(display_name,))
                else:
                    item_id = tree.insert("", "end", text=truncated_name, values=(display_name,))
                self.tree_item_to_program[(tree, item_id)] = program

            # --- Treeview Tooltip Logic ---
            tree_tooltip = None
            def on_tree_motion(event):
                nonlocal tree_tooltip
                item_id = tree.identify_row(event.y)
                if item_id:
                    full_text = tree.item(item_id, "values")[0]
                    # Only show tooltip if the text is actually truncated
                    if len(full_text) > max_len:
                        if not tree_tooltip:
                            tree_tooltip = ToolTip(tree, lambda: full_text)
                        tree_tooltip.text_func = lambda: full_text
                        tree_tooltip.schedule()
                    else:
                        if tree_tooltip:
                            tree_tooltip.hidetip()
                elif tree_tooltip:
                    tree_tooltip.hidetip()
            tree.bind('<Motion>', on_tree_motion)

        self.clear_details_panel()
        self.update_action_button_states()

    def on_program_selection(self, event):
        tree = event.widget
        selected_item = tree.selection()
        if selected_item:
            item_id = selected_item[0]
            program_key = (tree, item_id)
            if program_key in self.tree_item_to_program:
                self.selected_program = self.tree_item_to_program[program_key]
                self.display_details_panel(self.selected_program)
                self.update_action_button_states()
                return
        self.selected_program = None
        self.clear_details_panel()
        self.update_action_button_states()

    def display_details_panel(self, program_info):
        self.display_name_var.set(program_info.get("DisplayName", ""))
        self.exe_path_var.set(program_info.get("ExecutablePath", ""))
        self.install_location_var.set(program_info.get("InstallLocation", ""))      
        self.last_updated_var.set(program_info.get("LastUpdated", "N/A"))
        self.remote_last_updated_var.set("Checking...")
        self.nodes_list_url_var.set(program_info.get("NodesListURL", ""))
        self.nodes_list_target_var.set(program_info.get("NodesListTargetPath", ""))
        self.nodes_last_updated_var.set(program_info.get("NodesLastUpdated", "N/A"))
        self.nodes_remote_last_updated_var.set("Checking...")
        self.winmx_patch_url_var.set(program_info.get("WinMXPatchURL", ""))
        self.winmx_patch_target_var.set(program_info.get("WinMXPatchTarget", ""))
        self.winmx_patch_last_updated_var.set(program_info.get("WinMXPatchLastUpdated", "N/A"))
        self.winmx_remote_last_updated_var.set("Checking...")

        self._fetch_remote_update_times(program_info)

        is_edonkey_network = program_info.get("Network") == "eDonkey/Kadmille"
        
        # Show/Hide the Kademlia (nodes.dat) frame within the Server List tab
        # The section should be visible if the program is configured for it (i.e., has a target path),
        # not just based on its name. This is crucial for manually added clients.
        has_nodes_config = bool(program_info.get("NodesListTargetPath"))
        if has_nodes_config:
            # Show Kademlia frame only for eMule
            self.nodes_frame.grid(row=2, column=0, sticky='ew', pady=(10, 0), padx=2)
        else:
            self.nodes_frame.grid_remove()

        # Show/Hide the WinMX Patch frame
        is_winmx = "winmx" in program_info.get("DisplayName", "").lower()
        if is_winmx:
            self.winmx_patch_frame.grid(row=3, column=0, sticky='ew', pady=(10, 0), padx=2)
        else:
            self.winmx_patch_frame.grid_remove()

        # Always show the standard editor UI
        self.multi_url_frame.grid()
        self.download_server_list_button.grid(row=0, column=2, sticky='e')
        self.download_server_list_button.config(text="Download Sources")
        self.server_last_updated_label.grid()
        self.server_last_updated_value.grid()

        # --- Configure the Server List tab ---
        target_sources = program_info.get("ServerListTargetPaths", {})

        # Clear old tabs and widget references
        for tab in self.multi_url_notebook.tabs():
            self.multi_url_notebook.forget(tab)
        self.multi_url_widgets.clear()

        for url, paths in target_sources.items():
            # Use the first path's basename for the tab name, or a generic name
            tab_name = os.path.basename(paths[0]) if paths else "New Source" # Default
            if url.lower().endswith(".wsx") and not paths:
                tab_name = "OpenNapster .WSX"
            tab = ttk.Frame(self.multi_url_notebook, padding=10)
            self.multi_url_notebook.add(tab, text=tab_name)
            tab.grid_columnconfigure(1, weight=1)
            tab.grid_rowconfigure(1, weight=1)

            # URL Entry
            # We need to decide whether to show a Combobox (for eDonkey) or a regular Entry
            ttk.Label(tab, text="Download URL:").grid(row=0, column=0, sticky='w', pady=2)
            url_var = tk.StringVar(value=url)

            # Use a Combobox for all to allow both selection and free-form text entry.
            url_combo = ttk.Combobox(tab, textvariable=url_var) # state will be set in _update_server_fields_for_network
            url_combo.grid(row=0, column=1, sticky='ew', padx=5)

            # Add tooltip for the URL field
            ToolTip(url_combo, lambda v=url_var: v.get())

            test_button = ttk.Button(tab, text="Test", command=lambda u=url_var: self.test_url(u))
            test_button.grid(row=0, column=2, sticky='e')

            # Determine the list of available URLs for the dropdown
            available_urls = []
            network_custom_lists = self._get_custom_lists_for_network(program_info.get("Network"))
            if is_edonkey_network:
                combined_lists = {**self.EDONKEY_SERVER_LISTS, **network_custom_lists}
                available_urls = list(combined_lists.keys())
                url_combo.bind("<<ComboboxSelected>>", lambda e, v=url_var: self._on_server_url_select(v))
                # Set friendly name if URL matches either a default or custom list
                for name, url_val in combined_lists.items():
                    if url == url_val:
                        url_var.set(name)
                        break
            else:
                available_urls = list(network_custom_lists.keys())
                url_combo.bind("<<ComboboxSelected>>", lambda e, v=url_var: self._on_server_url_select(v))

            # Ensure the current URL (or its friendly name) is in the list of values
            if url_var.get() not in available_urls:
                available_urls.insert(0, url_var.get())
            url_combo['values'] = available_urls

            # Target Paths Treeview
            ttk.Label(tab, text="Target Paths:").grid(row=1, column=0, sticky='nw', pady=2)
            target_frame = ttk.Frame(tab) # No padding needed here
            target_frame.grid(row=1, column=1, columnspan=2, sticky='nsew')
            target_frame.grid_columnconfigure(0, weight=1)
            target_frame.grid_rowconfigure(0, weight=1)

            target_tree = ttk.Treeview(target_frame, height=3, selectmode="browse", show="tree")
            target_tree.grid(row=0, column=0, sticky="nsew")
            target_scrollbar = ttk.Scrollbar(target_frame, orient="vertical", command=target_tree.yview)
            target_scrollbar.grid(row=0, column=1, sticky="ns")
            target_tree.configure(yscrollcommand=target_scrollbar.set)
            target_tree.heading("#0", text="Path", anchor="w")

            # Add tooltip for the target treeview
            tree_tooltip = None
            def on_target_tree_motion(event):
                nonlocal tree_tooltip
                item_id = target_tree.identify_row(event.y)
                if item_id:
                    full_text = target_tree.item(item_id, "text")
                    if not tree_tooltip:
                        tree_tooltip = ToolTip(target_tree, lambda: full_text)
                    tree_tooltip.text_func = lambda: full_text
                    tree_tooltip.schedule()
                elif tree_tooltip:
                    tree_tooltip.hidetip()
            target_tree.bind('<Motion>', on_target_tree_motion)
            target_tree.bind("<Double-1>", self.on_target_tree_double_click)

            for path in paths:
                target_tree.insert("", "end", text=path)

            # Store widgets for later access
            self.multi_url_widgets.append({
                'url_var': url_var,
                'url_widget': url_combo,
                'test_button': test_button,
                'target_tree': target_tree,
                'tab': tab
            })

        # Also resolve friendly name for nodes.dat
        current_nodes_val = self.nodes_list_url_var.get()
        if current_nodes_val in self.EMULE_NODES_LISTS:
            self.nodes_list_url_var.set(self.EMULE_NODES_LISTS[current_nodes_val])

        # This MUST be called at the end, after all UI elements (like multi-URL tabs)
        # have been created, to ensure their states are set correctly.
        state = tk.NORMAL if self.is_editing else tk.DISABLED
        self.browse_exe_button.config(state=state)
        self.browse_install_button.config(state=state)
        self._update_server_fields_for_network(program_info)

    def _update_server_fields_for_network(self, program_info):
        """Enables, disables, or clears server fields based on network type and edit mode."""
        # The nodes.dat section should be available for any eDonkey client that has a nodes.dat target path configured,
        # not just for programs with "emule" in their name. This makes it work for manually added clients.
        has_nodes_config = bool(program_info.get("NodesListTargetPath"))
        is_winmx = "winmx" in program_info.get("DisplayName", "").lower()
        network = program_info.get("Network")
        is_edonkey_network = network == "eDonkey/Kadmille"

        # Show/hide the multi-URL source/target buttons based on edit mode
        self.add_multi_source_button.pack(side='left', padx=(0,5))
        self.add_target_button.pack(side='left', padx=(0,5))
        self.remove_target_button.pack(side='left', padx=(0,20))
        self.remove_multi_source_button.pack(side='left')

        state = tk.NORMAL if self.is_editing else tk.DISABLED

        # Update state for multi-URL tab widgets
        for widgets in self.multi_url_widgets:
            widget_state = tk.DISABLED
            if self.is_editing:
                # For combobox, 'normal' allows typing custom values. For entry, it's just 'normal'.
                widget_state = 'normal'
            # For comboboxes, 'readonly' is the correct state when not editing.
            elif isinstance(widgets['url_widget'], ttk.Combobox):
                 widget_state = 'readonly'
            widgets['url_widget'].config(state=widget_state)
            widgets['test_button'].config(state=tk.NORMAL if widgets['url_var'].get() else tk.DISABLED)
            # Treeview doesn't have a 'state', editing is handled by events
        self.add_multi_source_button.config(state=state)
        self.remove_multi_source_button.config(state=state)
        self.add_custom_url_button.config(state=state)
        self.remove_custom_url_button.config(state=state)

        self.add_target_button.config(state=state)
        self.remove_target_button.config(state=state)

        # Handle Kademlia (nodes.dat) fields - only for eMule
        nodes_state = tk.DISABLED
        nodes_combo_state = tk.DISABLED
        if is_edonkey_network and has_nodes_config:
            nodes_state = tk.NORMAL if self.is_editing else "readonly"
            # The combobox should be 'readonly' when not editing, and 'normal' when editing.
            nodes_combo_state = tk.NORMAL if self.is_editing else "readonly"

        self.nodes_list_url_entry.grid_remove()
        self.nodes_list_url_combo.grid()

        self.nodes_list_url_combo['values'] = list(self.EMULE_NODES_LISTS.keys()) + ["(Custom)"]
        self.nodes_list_url_combo.config(state=nodes_state)

        self.nodes_list_target_entry.config(state=nodes_state)
        self.browse_nodes_target_button.config(state=state)
        self.test_nodes_url_button.config(state=tk.NORMAL if self.nodes_list_url_var.get() else tk.DISABLED)

        # Handle WinMX Patch fields
        winmx_state = tk.DISABLED
        if is_winmx:
            winmx_state = tk.NORMAL if self.is_editing else tk.DISABLED
        self.winmx_patch_url_entry.config(state=winmx_state)
        self.winmx_patch_target_entry.config(state=winmx_state)
        self.test_winmx_patch_url_button.config(state=tk.NORMAL if self.winmx_patch_url_var.get() and winmx_state != tk.DISABLED else tk.DISABLED)
        self.browse_winmx_patch_target_button.config(state=winmx_state)

        # Also disable the download button if the fields are disabled
        self.on_nodes_list_url_change()
        self.update_download_button_state()

    def clear_details_panel(self):
        self.exe_path_var.set("")
        self.install_location_var.set("")
        # Clear multi-URL view
        for tab in self.multi_url_notebook.tabs():
            self.multi_url_notebook.forget(tab)
        self.multi_url_widgets.clear()
        self.nodes_frame.grid_remove() # Hide nodes frame
        self.winmx_patch_frame.grid_remove() # Hide WinMX patch frame
        self.last_updated_var.set("N/A")
        self.remote_last_updated_var.set("N/A")
        self.nodes_list_url_var.set("")
        self.nodes_list_target_var.set("")
        self.nodes_last_updated_var.set("N/A")
        self.nodes_remote_last_updated_var.set("N/A")
        self.winmx_patch_url_var.set("")
        self.winmx_patch_target_var.set("")
        self.winmx_patch_last_updated_var.set("N/A")
        self.winmx_remote_last_updated_var.set("N/A")
        self.download_server_list_button.config(state=tk.DISABLED)
        self.nodes_list_url_combo.config(state=tk.DISABLED)
        self.browse_exe_button.config(state=tk.DISABLED)
        self.browse_install_button.config(state=tk.DISABLED)
        self.display_name_var.set("")

    def update_action_button_states(self):
        if self.selected_program:
            self.launch_button.config(state=tk.NORMAL)
            self.open_config_button.config(state=tk.NORMAL)
            self.remove_program_button.config(state=tk.NORMAL)
            self.edit_button.config(state=tk.NORMAL)
        else:
            self.launch_button.config(state=tk.DISABLED)
            self.open_config_button.config(state=tk.DISABLED)
            self.remove_program_button.config(state=tk.DISABLED)
            self.edit_button.config(state=tk.DISABLED)

        # Handle edit mode buttons
        if self.is_editing:
            self.launch_button.config(state=tk.DISABLED)
            self.open_config_button.config(state=tk.DISABLED)
            self.remove_program_button.config(state=tk.DISABLED)

    def update_download_button_state(self):
        has_sources = len(self.multi_url_widgets) > 0

        if has_sources:
            self.download_server_list_button.config(state=tk.NORMAL)
        else:
            self.download_server_list_button.config(state=tk.DISABLED)

    def on_nodes_list_url_change(self, *args):
        # The download button should only be active if the fields are also active (not disabled)
        is_active = self.nodes_list_target_entry.cget("state") != tk.DISABLED

        if self.nodes_list_url_var.get() and self.nodes_list_target_var.get() and is_active:
            self.download_nodes_list_button.config(state=tk.NORMAL)
        else:
            self.download_nodes_list_button.config(state=tk.DISABLED)

    def _on_server_url_select(self, url_var):
        """
        Handles selection from any server list combobox to re-fetch the remote update time.
        """
        if not self.selected_program:
            return

        url_or_name = url_var.get()
        network = self.selected_program.get("Network")
        network_custom_lists = self._get_custom_lists_for_network(network)
        
        # Check all relevant lists for a friendly name match
        combined_lists = {**self.EDONKEY_SERVER_LISTS, **network_custom_lists}
        
        url_to_check = combined_lists.get(url_or_name, url_or_name)

        self.remote_last_updated_var.set("Checking...")
        threading.Thread(target=self._get_last_modified, args=(url_to_check, self.remote_last_updated_var), daemon=True).start()
        
    def on_winmx_patch_change(self, *args):
        is_active = self.winmx_patch_target_entry.cget("state") != tk.DISABLED
        has_url = self.winmx_patch_url_var.get()
        if has_url and self.winmx_patch_target_var.get() and is_active:
            self.download_winmx_patch_button.config(state=tk.NORMAL)
        else:
            self.download_winmx_patch_button.config(state=tk.DISABLED)
        self.test_winmx_patch_url_button.config(state=tk.NORMAL if has_url and is_active else tk.DISABLED)

    def on_nodes_list_select(self, event):
        """Handles selection from the eMule nodes.dat list combobox."""
        selection = self.nodes_list_url_var.get()
        if selection in self.EMULE_NODES_LISTS:
            self.nodes_list_url_var.set(self.EMULE_NODES_LISTS[selection])

    def add_program_manually(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add Program Manually")
        dialog.geometry("500x380")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.grid_columnconfigure(1, weight=1)

        # --- Widgets ---
        ttk.Label(frame, text="Executable:").grid(row=0, column=0, sticky="w", pady=2)
        exe_var = tk.StringVar()
        ttk.Entry(frame, textvariable=exe_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(frame, text="Display Name:").grid(row=1, column=0, sticky="w", pady=2)
        name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=name_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)

        ttk.Label(frame, text="Network:").grid(row=2, column=0, sticky="w", pady=2)
        network_var = tk.StringVar()
        network_combo = ttk.Combobox(frame, textvariable=network_var, state="readonly")
        network_combo['values'] = sorted(list(self.P2P_NETWORKS.keys()))
        network_combo.grid(row=2, column=1, columnspan=2, sticky="ew", padx=5)
        network_combo.set("Unknown") # Default value
        
        # --- Dynamic Prefill Options ---
        options_frame = ttk.LabelFrame(frame, text="Prefill Options", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 5))
        options_frame.grid_columnconfigure(0, weight=1)
        
        prefill_vars = {}
        nodes_target_var = tk.StringVar()
        nodes_url_friendly_name_var = tk.StringVar()
        nodes_url_custom_var = tk.StringVar()
        
        def update_prefill_options(*args):
            # Clear existing options
            for widget in options_frame.winfo_children():
                widget.destroy()
            prefill_vars.clear()
            
            nodes_target_var.set("")
            nodes_url_friendly_name_var.set("")
            nodes_url_custom_var.set("")
            network = network_var.get()
            options = []
            
            # More granular options based on network
            if network == "eDonkey/Kadmille":
                options = [("eDonkey Server List (server.met)", "edonkey_server"),
                           ("Kademlia Nodes List (nodes.dat for eMule/Lphant)", "edonkey_nodes")]
            elif network == "Gnutella":
                options = [("Gnutella Host Cache (gnutella.net)", "gnutella_cache")]
            elif network == "GnuCDNA/Gnutella2":
                options = [("Gnucleus Cache Files", "gnucdna_gnucleus"), # Also for XoloX
                           ("Morpheus Cache Files", "gnucdna_morpheus"),
                           ("Morpheus Ultra Cache Files", "gnucdna_morpheus_ultra"),
                           ("MyNapster Cache Files", "gnucdna_mynapster"),
                           ("Phex Host Caches", "gnucdna_phex"),
                           ("KCeasy Cache Files", "gnucdna_kceasy"),
                           ("XoloX Cache Files (uses Gnucleus files)", "gnucdna_xolox"),
                           ("NeoNapster Cache Files (uses Gnucleus files)", "gnucdna_neonapster")]
            elif network == "OpenNapster":
                options = [("Napigator Server List (.reg)", "opennap_napigator"),
                           ("FileNavigator Server List (.reg)", "opennap_filenavigator"),
                           ("Swaptor Server List (.reg)", "opennap_swaptor"),
                           ("Original Napster Client Config", "opennap_napster"),
                           ("Generic OpenNap Server List (.wsx)", "opennap_wsx")]
            elif network == "WinMX":
                options = [("WinMX Connection Patch (oledlg.dll)", "winmx_patch"), # Also for WinMX Community Patch
                           ("OpenNapster Server List (.wsx)", "winmx_opennap")]
            
            if not options:
                ttk.Label(options_frame, text="No prefill options for this network.", font=("Segoe UI", 9, "italic")).pack(anchor='w')
                return
            
            # Use a single variable for GnuCDNA/G2 since only one can be chosen
            gnucdna_var = tk.StringVar()
            prefill_vars["gnucdna_choice"] = gnucdna_var
            
            # --- Widgets for nodes.dat path ---
            nodes_frame = ttk.Frame(options_frame)
            nodes_frame.columnconfigure(1, weight=1) # Make entry/combo expand

            nodes_url_label = ttk.Label(nodes_frame, text="Nodes.dat URL:")
            nodes_url_combo = ttk.Combobox(nodes_frame, textvariable=nodes_url_friendly_name_var, state='readonly')
            nodes_url_combo['values'] = list(self.EMULE_NODES_LISTS.keys()) + ["(Custom)"]
            nodes_url_friendly_name_var.set(list(self.EMULE_NODES_LISTS.keys())[0]) # Set a default

            nodes_url_custom_entry = ttk.Entry(nodes_frame, textvariable=nodes_url_custom_var)
            
            def on_nodes_url_select(*args):
                # Always resolve the friendly name to its URL for the logic in on_ok
                selection = nodes_url_friendly_name_var.get()
                if selection in self.EMULE_NODES_LISTS:
                    nodes_url_custom_var.set(self.EMULE_NODES_LISTS[selection])
                else: # This handles the "(Custom)" case
                    nodes_url_custom_var.set("") # Clear it for the user to type

                if nodes_url_friendly_name_var.get() == "(Custom)":
                    nodes_url_custom_entry.grid(row=1, column=1, columnspan=2, sticky='ew', padx=5, pady=(2,0))
                    nodes_target_label.grid(row=2, column=0, sticky='w', pady=(2,0))
                    nodes_target_entry.grid(row=2, column=1, sticky='ew', padx=5, pady=(2,0))
                    nodes_browse_button.grid(row=2, column=2, pady=(2,0))
                else:
                    nodes_url_custom_entry.grid_remove()
                    nodes_target_label.grid(row=1, column=0, sticky='w', pady=(2,0))
                    nodes_target_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=(2,0))
                    nodes_browse_button.grid(row=1, column=2, pady=(2,0))
            nodes_url_friendly_name_var.trace_add("write", on_nodes_url_select)
            
            nodes_target_label = ttk.Label(nodes_frame, text="Nodes.dat Target:")
            nodes_target_entry = ttk.Entry(nodes_frame, textvariable=nodes_target_var)
            
            def browse_nodes_target():
                filepath = filedialog.asksaveasfilename(
                    title="Select nodes.dat Target Path",
                    initialdir=os.path.dirname(exe_var.get()) if exe_var.get() else os.path.expanduser("~"),
                    initialfile="nodes.dat",
                    filetypes=[("Data files", "*.dat"), ("All files", "*.*")],
                    parent=dialog
                )
                if filepath:
                    nodes_target_var.set(filepath)
            nodes_browse_button = ttk.Button(nodes_frame, text="...", width=3, command=browse_nodes_target)

            for text, key in options:
                if key.startswith("gnucdna_"):
                    # Use radio buttons for exclusive choices
                    rb = ttk.Radiobutton(options_frame, text=text, variable=gnucdna_var, value=key)
                    rb.pack(anchor='w', padx=5)
                else:
                    # Use checkboxes for non-exclusive choices
                    var = tk.BooleanVar(value=True)
                    prefill_vars[key] = var
                    chk = ttk.Checkbutton(options_frame, text=text, variable=var)
                    chk.pack(anchor='w', padx=5)

                    # If this is the nodes.dat checkbox, show the path entry when checked
                    if key == "edonkey_nodes":
                        def toggle_nodes_path_entry(*args):
                            if var.get():
                                nodes_frame.pack(fill='x', padx=20, pady=(0, 5)) # Indent it under the checkbox
                            else:
                                nodes_frame.pack_forget()
                        var.trace_add("write", toggle_nodes_path_entry)
                        nodes_url_label.grid(row=0, column=0, sticky='w', pady=(0,2))
                        nodes_url_combo.grid(row=0, column=1, columnspan=2, sticky='ew', padx=5, pady=(0,2))
                        # Initial call to set the layout correctly based on the default selection
                        on_nodes_url_select()

        
        network_var.trace_add("write", update_prefill_options)
        update_prefill_options() # Initial call

        # --- Functions for Dialog ---
        def browse_exe():
            filepath = filedialog.askopenfilename(
                title="Select Program Executable (EXE or JAR)",
                filetypes=[("Executable files", "*.exe *.jar"), ("All files", "*.*")]
            )
            if filepath:
                exe_var.set(filepath)
                name_var.set(os.path.splitext(os.path.basename(filepath))[0])

        def on_ok():
            filepath = exe_var.get()
            display_name = name_var.get()
            network = network_var.get()

            if not filepath or not display_name:
                messagebox.showwarning("Missing Information", "Please provide both an executable and a display name.", parent=dialog)
                return

            # Check for duplicates (same path on the same network)
            if any(p.get("ExecutablePath") == filepath and p.get("Network") == network for p in self.installed_programs):
                messagebox.showwarning("Duplicate", f"This program is already listed under the '{network}' network.", parent=dialog)
                return

            program_info = {
                "DisplayName": display_name,
                "InstallLocation": os.path.dirname(filepath),
                "ExecutablePath": filepath,
                "ServerListURL": "",
                "ServerListTargetPaths": {},
                "Source": "Manual",
                "Network": network,
                "NodesListURL": "",
                "NodesLastUpdated": "N/A",
                "WinMXPatchURL": "",
                "WinMXPatchTarget": "",
                "WinMXPatchLastUpdated": "N/A",
                "NodesListTargetPath": "",
            }
            
            # --- Conditionally prefill based on selections ---
            
            # eDonkey: Handle multiple selections correctly
            prefill_server = prefill_vars.get("edonkey_server", tk.BooleanVar(value=False)).get()
            prefill_nodes = prefill_vars.get("edonkey_nodes", tk.BooleanVar(value=False)).get()
            if prefill_server or prefill_nodes:
                # Provide a hint for the client type based on the checkbox.
                # The custom var already holds the resolved URL or the custom user input
                nodes_url = nodes_url_custom_var.get()
                # The friendly name is used for display in the main UI
                nodes_url_friendly_name = nodes_url_friendly_name_var.get()
                
                edonkey_client_type = "emule" if prefill_nodes else "generic" # This logic remains correct
                self._prefill_edonkey_info(program_info, prefill_server=prefill_server, prefill_nodes=prefill_nodes,
                                           client_type=edonkey_client_type, nodes_target_override=nodes_target_var.get(),
                                           nodes_url_override=nodes_url)

            # Gnutella
            if prefill_vars.get("gnutella_cache", tk.BooleanVar(value=False)).get():
                self._prefill_gnutella_info(program_info)

            # GnuCDNA/G2 (uses radio buttons)
            gnucdna_choice = prefill_vars.get("gnucdna_choice", tk.StringVar()).get()
            if gnucdna_choice:
                self._prefill_gnucdna_info(program_info, client_type=gnucdna_choice.split('_')[-1])
                if gnucdna_choice == "gnucdna_neonapster":
                    self._prefill_gnucdna_info(program_info, client_type="neonapster")

            # OpenNapster
            if prefill_vars.get("opennap_napigator", tk.BooleanVar(value=False)).get():
                self._prefill_opennap_info(program_info, client_type="napigator")
            if prefill_vars.get("opennap_filenavigator", tk.BooleanVar(value=False)).get():
                self._prefill_opennap_info(program_info, client_type="filenavigator")
            if prefill_vars.get("opennap_swaptor", tk.BooleanVar(value=False)).get():
                self._prefill_opennap_info(program_info, client_type="swaptor")
            if prefill_vars.get("opennap_napster", tk.BooleanVar(value=False)).get():
                self._prefill_opennap_info(program_info, client_type="napster")
            if prefill_vars.get("opennap_wsx", tk.BooleanVar(value=False)).get():
                self._prefill_opennap_info(program_info, client_type="wsx")

            # WinMX
            if prefill_vars.get("winmx_patch", tk.BooleanVar(value=False)).get():
                self._prefill_winmx_info(program_info, prefill_patch=True)
            if prefill_vars.get("winmx_opennap", tk.BooleanVar(value=False)).get():
                self._prefill_winmx_info(program_info, prefill_wsx=True)
            
            self.installed_programs.append(program_info)
            self._update_program_list_ui()
            self.log_message(f"Manually added '{display_name}' to '{network}' network.")
            self.save_settings()
            dialog.destroy()

        # --- Buttons ---
        ttk.Button(frame, text="Browse...", command=browse_exe).grid(row=0, column=2)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(10, 0), sticky='e')
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def _prefill_opennap_info(self, program_info, client_type=None):
        """Checks if a program is an OpenNap client and pre-fills server info."""
        if program_info.get("Network") != "OpenNapster":
            return

        display_name = program_info.get("DisplayName", "").lower()

        # Auto-detect from display name if type isn't specified
        if not client_type:
            if "napigator" in display_name:
                client_type = "napigator"
            elif "filenavigator" in display_name:
                client_type = "filenavigator"
            elif "swaptor" in display_name:
                client_type = "swaptor"
            elif "napster" in display_name and "mynapster" not in display_name:
                client_type = "napster"

        if client_type == "napigator":
            # Override paths for Napigator to ensure correctness, as registry can be unreliable.
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            if program_info.get("Source") == "Registry":
                install_path = os.path.join(program_files_x86, "thirty4 interactive", "Napigator")
                # The main executable is a shortcut, which is fine for display, but we point to the folder.
                exe_path = os.path.join(install_path, "Standalone.lnk")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            # Napigator uses a .reg file for its server list.
            reg_url = "https://raw.githubusercontent.com/GamerA1-99/Napigator-server/main/Napigator%20server%20bookmarks.reg"
            program_info["ServerListTargetPaths"] = {
                reg_url: ["(Windows Registry)"] # This is a virtual path
            }
            icon_filename = "Napigator.ico"
            if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                program_info["IconPath"] = icon_filename
        elif client_type == "filenavigator":
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            if program_info.get("Source") == "Registry":
                install_path = os.path.join(program_files_x86, "FileNavigator")
                exe_path = os.path.join(install_path, "FileNavigator.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            # FileNavigator also uses a .reg file for its server list.
            reg_url = "https://raw.githubusercontent.com/GamerA1-99/FileNavigator/FileNavigator/filenavigator.reg"
            program_info["ServerListTargetPaths"] = {
                reg_url: ["(Windows Registry)"] # This is a virtual path
            }

        elif client_type == "swaptor":
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            if program_info.get("Source") == "Registry":
                install_path = os.path.join(program_files_x86, "Swaptor")
                exe_path = os.path.join(install_path, "Swaptor.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            # Swaptor also uses a .reg file for its server list.
            reg_url = "https://raw.githubusercontent.com/GamerA1-99/FileNavigator/Swaptor/filenavigator.reg"
            program_info["ServerListTargetPaths"] = {
                reg_url: ["(Windows Registry)"] # This is a virtual path
            }

        elif client_type == "napster":
            # This handles the original Napster client.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "Napster")
                exe_path = os.path.join(install_path, "napster.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
        elif client_type == "wsx":
            # Generic .wsx file for clients that support it (like WinMX, XNap)
            wsx_url = "https://raw.githubusercontent.com/GamerA1-99/Open-Napster-WSX/main/Public%20James%2020262201.wsx"
            # Add with an empty target list, allowing the user to add a save location.
            if wsx_url not in program_info["ServerListTargetPaths"]:
                program_info["ServerListTargetPaths"][wsx_url] = []

    def _prefill_winmx_info(self, program_info, prefill_patch=False, prefill_wsx=False):
        """Prefills information for WinMX."""
        if program_info.get("Network") != "WinMX":
            return

        display_name = program_info.get("DisplayName", "").lower()

        # Auto-detect from display name if no specific prefill is requested
        if not prefill_patch and not prefill_wsx:
            if "winmx" in display_name:
                prefill_patch = True
                prefill_wsx = True

        if prefill_patch:
            # This handles both "WinMX" and "WinMX Community Patch".
            # It downloads a patched DLL for network connectivity.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "WinMX")
                exe_path = os.path.join(install_path, "WinMX.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            program_info["WinMXPatchURL"] = "https://raw.githubusercontent.com/GamerA1-99/WinMX-Patch/main/oledlg.dll"
            program_info["WinMXPatchTarget"] = os.path.join(program_files_x86, "WinMX", "OLEDLG.DLL")

        if prefill_wsx:
            # Add the .wsx server list for connecting to the OpenNapster network.
            wsx_url = "https://raw.githubusercontent.com/GamerA1-99/Open-Napster-WSX/main/Public%20James%2020262201.wsx"
            if wsx_url not in program_info["ServerListTargetPaths"]:
                program_info["ServerListTargetPaths"][wsx_url] = []
            if "OpenNapster" not in program_info.get("AlsoInNetworks", []):
                program_info.setdefault("AlsoInNetworks", []).append("OpenNapster")

    def _prefill_gnutella_info(self, program_info):
        """Prefills server info for Gnutella clients."""
        if program_info.get("Network") != "Gnutella":
            return

        display_name = program_info.get("DisplayName", "")
        gnutella_keywords = ["limewire", "frostwire", "wireshare", "luckywire", "lemonwire", "turbowire", "cabos", "dexterwire"] # Known clients with predictable paths
        is_known_gnutella_client = False

        for kw in gnutella_keywords:
            if kw in display_name.lower():
                # It's a known Gnutella client, pre-fill the server list info.
                is_known_gnutella_client = True
                program_info["ServerListURL"] = "https://raw.githubusercontent.com/GamerA1-99/gnutella.net/main/gnutella.net"
                target_path = os.path.join(os.environ['APPDATA'], kw.capitalize(), "gnutella.net") # Default for most LimeWire forks
                program_info["ServerListTargetPaths"] = {
                    "https://raw.githubusercontent.com/GamerA1-99/gnutella.net/main/gnutella.net": [target_path]
                }
                if program_info.get("Source") == "Registry":
                    if kw == "limewire":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "LimeWire")
                        exe_path = os.path.join(install_path, "LimeWire.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                        icon_filename = "LimeWire.ico"
                        if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                            program_info["IconPath"] = icon_filename
                    elif kw == "frostwire":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "FrostWire")
                        exe_path = os.path.join(install_path, "FrostWire.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                    elif kw == "wireshare":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "WireShare")
                        exe_path = os.path.join(install_path, "WireShare.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                    elif kw == "luckywire":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "LuckyWire")
                        exe_path = os.path.join(install_path, "LuckyWire.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                        icon_filename = "LuckyWire.ico"
                        if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                            program_info["IconPath"] = icon_filename
                    elif kw == "lemonwire":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "LemonWire")
                        exe_path = os.path.join(install_path, "LemonWire.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                        # Use the LimeWire icon for LemonWire as requested
                        icon_filename = "LemonWire.ico"
                        if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                            program_info["IconPath"] = icon_filename
                    elif kw == "turbowire":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "TurboWire")
                        exe_path = os.path.join(install_path, "TurboWire.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                        icon_filename = "TurboWire.ico"
                        if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                            program_info["IconPath"] = icon_filename
                    elif kw == "cabos":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "Cabos")
                        exe_path = os.path.join(install_path, "Cabos.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                        icon_filename = "Cabos.ico"
                        if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                            program_info["IconPath"] = icon_filename
                        # Update the target path specifically for Cabos
                        cabos_target_path = os.path.join(os.environ['APPDATA'], "Cabos", "gnutella.net")
                        program_info["ServerListTargetPaths"] = {program_info.get("ServerListURL", "https://raw.githubusercontent.com/GamerA1-99/gnutella.net/main/gnutella.net"): [cabos_target_path]}
                    elif kw == "dexterwire":
                        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                        install_path = os.path.join(program_files_x86, "DexterWire")
                        exe_path = os.path.join(install_path, "DexterWire.exe")
                        program_info["InstallLocation"] = install_path
                        program_info["ExecutablePath"] = exe_path
                        # Update the target path specifically for DexterWire
                        icon_filename = "DexterWire.ico"
                        if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                            program_info["IconPath"] = icon_filename
                        dexterwire_target_path = os.path.join(os.environ['APPDATA'], "DexterWire", "gnutella.net")
                        program_info["ServerListTargetPaths"] = {program_info.get("ServerListURL", "https://raw.githubusercontent.com/GamerA1-99/gnutella.net/main/gnutella.net"): [dexterwire_target_path]}


                break

        # Handle manually added clients that are not in the known list
        if not is_known_gnutella_client and program_info.get("Source") == "Manual":
            url = "https://raw.githubusercontent.com/GamerA1-99/gnutella.net/main/gnutella.net"
            # Since we don't know the client, we can't guess the path.
            # Prompt the user to specify where to save the gnutella.net file.
            initial_dir = program_info.get("InstallLocation", os.path.expanduser("~"))
            filepath = filedialog.asksaveasfilename(
                title="Select where to save gnutella.net",
                initialdir=initial_dir,
                initialfile="gnutella.net",
                filetypes=[("Gnutella Host Cache", "gnutella.net"), ("All files", "*.*")]
            )
            if filepath:
                program_info["ServerListTargetPaths"] = {url: [filepath]}
            else:
                # If user cancels, add the source with an empty target list
                program_info["ServerListTargetPaths"] = {url: []}
        
        # Specifically clear server info for clients like xNap that don't use a server list.
        # This should not affect other clients that might be in the Gnutella family but have their own logic (like Morpheus).
        if "xnap" in display_name:
            # The registry path for XNap can be unreliable, so we set it here for consistency.
            if program_info.get("Source") == "Registry" or "xnap" in program_info.get("MatchedKeyword", ""):
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "XNap")
                exe_path = os.path.join(install_path, "xnap.jar")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            # Add the .wsx server list for the OpenNapster network.
            # This file must be manually imported, so we add it as a source
            # with an empty target list, allowing the user to add a save location.
            wsx_url = "https://raw.githubusercontent.com/GamerA1-99/Open-Napster-WSX/main/Public%20James%2020262201.wsx"
            program_info["ServerListTargetPaths"] = {wsx_url: []}
            program_info.setdefault("AlsoInNetworks", []).append("OpenNapster")
            # Explicitly set the icon for XNap
            icon_filename = "XNap.ico"
            if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                program_info["IconPath"] = icon_filename

    def _prefill_edonkey_info(self, program_info, prefill_server=True, prefill_nodes=True, client_type=None, nodes_target_override=None, nodes_url_override=None):
        """Checks if a program is an eDonkey client and pre-fills server info."""
        if program_info.get("Network") != "eDonkey/Kadmille":
            return

        display_name = program_info.get("DisplayName", "").lower()
        install_location = program_info.get("InstallLocation", "")

        # Auto-detect client type from name if not provided (e.g., from registry scan)
        if not client_type:
            if "edonkey2000" in display_name:
                client_type = "edonkey2000"
            elif "emule" in display_name:
                client_type = "emule"
            elif "lphant" in display_name:
                client_type = "lphant"
            else:
                client_type = "generic"

        if prefill_server:
            # Set default URL for eDonkey clients if not already set
            program_info.setdefault("ServerListURL", self.EDONKEY_SERVER_LISTS["eMule Security"])
            
            if client_type == "edonkey2000":
                target_path = os.path.join(install_location, "server.met")
                program_info["ServerListTargetPaths"] = {
                    self.EDONKEY_SERVER_LISTS["eMule Security"]: [target_path]
                }
            elif client_type == "emule":
                target_path = os.path.join(install_location, "config", "server.met")
                program_info["ServerListTargetPaths"] = {
                    self.EDONKEY_SERVER_LISTS["eMule Security"]: [target_path]
                }
            elif client_type == "lphant":
                server_target_path = os.path.join(install_location, "server.met")
                program_info["ServerListTargetPaths"] = {
                    self.EDONKEY_SERVER_LISTS["eMule Security"]: [server_target_path]
                }
            else:
                program_info.setdefault("ServerListTargetPaths", {self.EDONKEY_SERVER_LISTS["eMule Security"]: []})

        if prefill_nodes and client_type == "emule":
            if nodes_url_override:
                program_info["NodesListURL"] = nodes_url_override
            else:
                program_info["NodesListURL"] = "eMule Security" # Use friendly name

            if nodes_target_override:
                program_info["NodesListTargetPath"] = nodes_target_override
            else:
                program_info["NodesListTargetPath"] = os.path.join(install_location, "config", "nodes.dat")

        if prefill_nodes and client_type == "lphant":
            program_info["NodesListURL"] = "eMule Security" # Use friendly name
            if nodes_target_override:
                program_info["NodesListTargetPath"] = nodes_target_override
            else:
                # C:\Users\<user>\AppData\Local\Lphant\nodes.dat
                program_info["NodesListTargetPath"] = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Lphant', 'nodes.dat')

            # Add icon path if it exists
            icon_filename = "lphant.ico"
            if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                program_info["IconPath"] = icon_filename
        elif client_type == "emule":
            icon_filename = "eMule.ico"
            if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                program_info["IconPath"] = icon_filename
        elif client_type == "edonkey2000":
            icon_filename = "eDonkey.ico"
            if os.path.exists(os.path.join(self.script_dir, icon_filename)):
                program_info["IconPath"] = icon_filename

        # To display the friendly name, we find which key corresponds to the current URL
        # This runs for all eDonkey clients to ensure the dropdown shows the name, not the URL.
        current_url = program_info.get("ServerListURL")
        for name, url_val in self.EDONKEY_SERVER_LISTS.items():
            if current_url == url_val:
                program_info["ServerListURL"] = name # Store the friendly name for display
                break

    def _prefill_gnucdna_info(self, program_info, client_type=None):
        """Prefills server info for GnuCDNA/G2 clients.
        `client_type` can be 'morpheus', 'gnucleus', 'phex', etc.
        """
        if program_info.get("Network") != "GnuCDNA/Gnutella2":
            return

        display_name = program_info.get("DisplayName", "").lower()
        app_data_path = os.environ.get('APPDATA')

        if not app_data_path:
            return

        # Auto-detect from display name if type isn't specified
        if not client_type:
            for kw in ["morpheus ultra", "morpheus", "gnucleus", "mynapster", "phex", "xolox", "kceasy", "neonapster", "bearshare"]:
                if kw in display_name:
                    client_type = kw.replace(" ", "_") # e.g., "morpheus ultra" -> "morpheus_ultra"

        if client_type == "morpheus_ultra":
            # Morpheus Ultra has multiple, distinct server files.
            # We will store these as a dictionary of {url: [target_paths]}
            # The UI will show "Multiple Sources" and the download logic will handle it.
            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/Morpheus-Ultra/"
            morpheus_ultra_dir = os.path.join(app_data_path, "Morpheus Ultra")
            morpheus_dir = os.path.join(app_data_path, "Morpheus")
            program_info["ServerListURL"] = "Multiple Sources" # Special value for UI
            program_info["ServerListTargetPaths"] = {
                base_url + "MorphBlocked.net": [os.path.join(morpheus_ultra_dir, "MorphBlocked.net"),
                                               os.path.join(morpheus_dir, "MorphBlocked.net")],
                base_url + "MorphCache.net": [os.path.join(morpheus_ultra_dir, "MorphCache.net"),
                                             os.path.join(morpheus_dir, "MorphCache.net")],
                base_url + "MorphUltraCache.net": [os.path.join(morpheus_ultra_dir, "MorphUltraCache.net"),
                                                  os.path.join(morpheus_dir, "MorphUltraCache.net")],
                base_url + "WebCache.net": [os.path.join(morpheus_ultra_dir, "WebCache.net"),
                                           os.path.join(morpheus_dir, "WebCache.net")],
            }
            program_info["ServerListType"] = "multi"
        elif client_type == "morpheus":
            # Override paths for standard Morpheus to ensure correctness, as registry can be unreliable.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "Morpheus")
                exe_path = os.path.join(install_path, "Morpheus.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            # Standard Morpheus has multiple, distinct server files, similar to Ultra.
            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/Morepheus/"
            morpheus_dir = os.path.join(app_data_path, "Morpheus")
            program_info["ServerListURL"] = "Multiple Sources" # Special value for UI
            program_info["ServerListTargetPaths"] = {
                base_url + "MorphBlocked.net": [os.path.join(morpheus_dir, "MorphBlocked.net")],
                base_url + "MorphCache.net": [os.path.join(morpheus_dir, "MorphCache.net")],
                base_url + "WebCache.net": [os.path.join(morpheus_dir, "WebCache.net")],
            }
            program_info["ServerListType"] = "multi"
        elif client_type == "gnucleus":
            # Gnucleus also has multiple server files, typically in its installation directory.
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            gnucleus_data_dir = os.path.join(program_files_x86, "Gnucleus", "Data")
            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/Gnucleus/"
            program_info["ServerListURL"] = "Multiple Sources" # Special value for UI
            program_info["ServerListTargetPaths"] = {
                base_url + "GnuBlocked.net": [os.path.join(gnucleus_data_dir, "GnuBlocked.net")],
                base_url + "WebCache.net": [os.path.join(gnucleus_data_dir, "WebCache.net")],
                base_url + "gnucache.net": [os.path.join(gnucleus_data_dir, "gnucache.net")],
            }
            program_info["ServerListType"] = "multi"
        elif client_type == "xolox":
            # XoloX uses the same files as Gnucleus, but in its own directory.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "XoloX")
                exe_path = os.path.join(install_path, "Xolox.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            xolox_data_dir = os.path.join(program_info["InstallLocation"], "data")

            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/Gnucleus/" # Uses Gnucleus files
            program_info["ServerListURL"] = "Multiple Sources"
            program_info["ServerListTargetPaths"] = {
                base_url + "GnuBlocked.net": [os.path.join(xolox_data_dir, "GnuBlocked.net")],
                base_url + "WebCache.net": [os.path.join(xolox_data_dir, "WebCache.net")],
                base_url + "gnucache.net": [os.path.join(xolox_data_dir, "gnucache.net")],
            }
        elif client_type == "neonapster":
            # NeoNapster uses the same files as Gnucleus, but in its own directory.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "NeoNapster")
                exe_path = os.path.join(install_path, "NeoNapster.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            neonapster_data_dir = os.path.join(program_info["InstallLocation"], "data")

            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/Gnucleus/" # Uses Gnucleus files
            program_info["ServerListTargetPaths"] = {
                base_url + "GnuBlocked.net": [os.path.join(neonapster_data_dir, "GnuBlocked.net")],
                base_url + "WebCache.net": [os.path.join(neonapster_data_dir, "WebCache.net")],
                base_url + "gnucache.net": [os.path.join(neonapster_data_dir, "gnucache.net")],
            }
        elif client_type == "mynapster":
            # The registry often finds "MyNapster (Remove only)". We correct the display name here.
            if "mynapster (remove only)" in display_name:
                program_info["DisplayName"] = "MyNapster"

            # Override paths for MyNapster to ensure correctness.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "MyNapster")
                exe_path = os.path.join(install_path, "MyNapster.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            data_path = os.path.join(program_info.get("InstallLocation", ""), "Data")
            # MyNapster has multiple, distinct server files.
            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/MyNapster/"
            program_info["ServerListURL"] = "Multiple Sources" # Special value for UI
            program_info["ServerListTargetPaths"] = {
                base_url + "GnuBlocked.net": [os.path.join(data_path, "GnuBlocked.net")],
                base_url + "MNCache.net": [os.path.join(data_path, "MNCache.net")],
                base_url + "MNUltraCache.net": [os.path.join(data_path, "MNUltraCache.net")],
                base_url + "WebCache.net": [os.path.join(data_path, "WebCache.net")],
            }
            program_info["ServerListType"] = "multi"
        elif client_type == "phex":
            # Override paths for Phex to ensure correctness.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "Phex")
                exe_path = os.path.join(install_path, "Phex.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            # Phex uses multiple host cache files.
            phex_appdata_dir = os.path.join(app_data_path, "Phex")
            base_url = "https://raw.githubusercontent.com/GamerA1-99/GnucDNA/Phex/"
            program_info["ServerListURL"] = "Multiple Sources" # Special value for UI
            program_info["ServerListTargetPaths"] = {
                base_url + "gwebcache.cfg": [os.path.join(phex_appdata_dir, "gwebcache.cfg")],
                base_url + "phex.hosts": [os.path.join(phex_appdata_dir, "phex.hosts")],
                base_url + "udphostcache.cfg": [os.path.join(phex_appdata_dir, "udphostcache.cfg")],
            }
            program_info["ServerListType"] = "multi"
        elif client_type == "kceasy":
            # KCeasy uses a giFT backend and has its own cache files.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                install_path = os.path.join(program_files_x86, "KCeasy")
                exe_path = os.path.join(install_path, "KCeasy.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path
            
            install_path = program_info.get("InstallLocation", "")
            conf_dir = os.path.join(install_path, "giFT", "conf", "Gnutella")
            program_info["ServerListTargetPaths"] = {
                "https://raw.githubusercontent.com/GamerA1-99/KCeasy/Gnutella/gwebcaches": [os.path.join(conf_dir, "gwebcaches")],
                "https://raw.githubusercontent.com/GamerA1-99/KCeasy/Gnutella/nodes": [os.path.join(conf_dir, "nodes")],
            }

        elif client_type == "bearshare":
            is_test_version = "test" in display_name
            # Override paths for BearShare to ensure correctness.
            if program_info.get("Source") == "Registry":
                program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
                # The installer might create "BearShare" or "BearShare Test"
                install_path_base = "BearShare Test" if is_test_version else "BearShare"
                install_path = os.path.join(program_files_x86, install_path_base)
                exe_path = os.path.join(install_path, "BearShare.exe")
                program_info["InstallLocation"] = install_path
                program_info["ExecutablePath"] = exe_path

            install_path = program_info.get("InstallLocation", "")
            db_dir = os.path.join(install_path, "db")
            base_url = "https://raw.githubusercontent.com/GamerA1-99/BearShare-Hosts-File/main/"

            if is_test_version:
                # BearShare Test uses a smaller set of files
                program_info["ServerListTargetPaths"] = {
                    base_url + "connect.txt": [os.path.join(db_dir, "connect.txt")],
                    base_url + "gwebcache.dat": [os.path.join(db_dir, "gwebcache.dat")],
                }
            else:
                # Regular BearShare uses four files
                program_info["ServerListTargetPaths"] = {
                    base_url + "connect.dat": [os.path.join(db_dir, "connect.dat")],
                    base_url + "connect.txt": [os.path.join(db_dir, "connect.txt")],
                    base_url + "gnucache.dat": [os.path.join(db_dir, "gnucache.dat")],
                    base_url + "gwebcache.dat": [os.path.join(db_dir, "gwebcache.dat")],
                }

    def toggle_edit_mode(self):
        self.is_editing = not self.is_editing

        if self.is_editing:
            # --- Enter Edit Mode ---
            self.edit_button.pack_forget() # Hide Edit button
            self.save_button.pack(side=tk.LEFT, padx=(5, 5))
            self.cancel_button.pack(side=tk.LEFT, padx=(0, 5))
            
            # Make fields editable
            self.display_name_entry.config(state=tk.NORMAL)
            self.exe_path_entry.config(state=tk.NORMAL)
            self.install_location_entry.config(state=tk.NORMAL)
            self.browse_exe_button.config(state=tk.NORMAL)
            self.browse_install_button.config(state=tk.NORMAL)
            if self.selected_program:
                self._update_server_fields_for_network(self.selected_program)
        else:
            # --- Exit Edit Mode (Cancel) ---
            self.save_button.pack_forget()
            self.cancel_button.pack_forget()
            self.edit_button.pack(side=tk.LEFT, padx=(5, 5))

            # Make fields read-only
            self.display_name_entry.config(state="readonly")
            self.exe_path_entry.config(state="readonly")
            self.install_location_entry.config(state="readonly")

            # Restore original data
            if self.selected_program:
                self.display_details_panel(self.selected_program)

        self.update_action_button_states()

    def save_edited_program(self):
        if not self.selected_program:
            return

        # Update program data from the entry fields
        self.selected_program["DisplayName"] = self.display_name_var.get()
        self.selected_program["ExecutablePath"] = self.exe_path_var.get()
        self.selected_program["InstallLocation"] = self.install_location_var.get()
        
        # Rebuild the ServerListTargetPaths dictionary from the UI widgets
        new_sources = {}
        for widgets in self.multi_url_widgets:
            url = widgets['url_var'].get()
            # If a friendly name is in the URL field, convert it back to a URL for saving
            network_custom_lists = self._get_custom_lists_for_network(self.selected_program.get("Network"))
            combined_lists = {**self.EDONKEY_SERVER_LISTS, **network_custom_lists}
            if url in combined_lists:
                url = combined_lists[url]

            paths = [widgets['target_tree'].item(item, "text") for item in widgets['target_tree'].get_children()]
            if url: # Only save sources that have a URL
                new_sources[url] = paths
        self.selected_program["ServerListTargetPaths"] = new_sources

        self.selected_program["NodesListURL"] = self.nodes_list_url_var.get()
        self.selected_program["NodesListTargetPath"] = self.nodes_list_target_var.get()
        self.selected_program["WinMXPatchURL"] = self.winmx_patch_url_var.get()
        self.selected_program["WinMXPatchTarget"] = self.winmx_patch_target_var.get()
        # Last updated fields are not saved here, they are updated on successful download

        # Also convert nodes.dat friendly name back to URL
        if self.selected_program["NodesListURL"] in self.EMULE_NODES_LISTS:
            self.selected_program["NodesListURL"] = self.EMULE_NODES_LISTS[self.selected_program["NodesListURL"]]

        
        # Mark as manually managed so it gets saved
        self.selected_program["Source"] = "Manual"

        self.log_message(f"Saved changes for {self.selected_program['DisplayName']}")
        self.save_settings()
        self._update_program_list_ui() # Refresh list to show new name if changed
        self.toggle_edit_mode() # Exit edit mode

    def remove_program(self):
        if not self.selected_program:
            messagebox.showwarning("Invalid Action", "Please select a program to remove.")
            return
        
        if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove '{self.selected_program['DisplayName']}' from the list? This will not uninstall the program."):
            program_to_remove = self.selected_program
            
            # If the program was auto-detected (i.e., has a registry key), ask if we should hide it from future scans.
            reg_key = program_to_remove.get("RegistryKey")
            if reg_key and program_to_remove.get("Source") != "Manual":
                if messagebox.askyesno("Hide Program?", "Do you want to prevent this program from being detected in future registry scans?"):
                    if reg_key not in self.hidden_registry_keys:
                        self.hidden_registry_keys.append(reg_key)
                    self.log_message(f"'{program_to_remove['DisplayName']}' will be hidden from future scans.")

            self.installed_programs.remove(self.selected_program)
            self._update_program_list_ui()
            self.log_message(f"Removed program: {program_to_remove['DisplayName']}")
            self.save_settings()

    def launch_selected_program(self):
        if not self.selected_program:
            messagebox.showwarning("No Selection", "Please select a program from the list first.")
            return

        exe_path = self.selected_program.get("ExecutablePath")
        if not exe_path or not os.path.exists(exe_path):
            messagebox.showerror("Launch Error", f"Executable path not found or invalid for {self.selected_program['DisplayName']}.")
            return

        try:
            if exe_path.lower().endswith(".jar"):
                # Check if Java is in PATH
                if shutil.which("java"):
                    command = ["java", "-jar", exe_path]
                    self.log_message(f"Attempting to launch JAR: {' '.join(command)}")
                    # Use DETACHED_PROCESS for Java apps as well
                    subprocess.Popen(command, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
                else:
                    messagebox.showerror("Launch Error", "Java Runtime Environment (JRE) not found. Please install Java to run JAR files.")
                    return
            else:
                # For .exe and .lnk files, os.startfile() is the most reliable way on Windows.
                # It correctly handles shortcuts and user-level file associations.
                self.log_message(f"Attempting to launch via shell: {exe_path}")
                os.startfile(exe_path)
            self.log_message(f"Successfully launched {self.selected_program['DisplayName']}.")
        except Exception as e:
            self.log_message(f"Failed to launch {self.selected_program['DisplayName']}: {e}")
            messagebox.showerror("Launch Error", f"Could not launch {self.selected_program['DisplayName']}:\n{e}")

    def browse_executable_path(self):
        initial_dir = self.install_location_var.get()
        if not initial_dir or not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")

        filepath = filedialog.askopenfilename(
            title="Select Program Executable",
            initialdir=initial_dir,
            filetypes=[("Executable files", "*.exe *.jar"), ("All files", "*.*")]
        )
        if filepath:
            self.exe_path_var.set(filepath)
            # Also update install location if it's empty
            if not self.install_location_var.get():
                self.install_location_var.set(os.path.dirname(filepath))

    def browse_install_location(self):
        initial_dir = self.install_location_var.get()
        if not initial_dir or not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")

        folderpath = filedialog.askdirectory(
            title="Select Installation Folder",
            initialdir=initial_dir
        )
        if folderpath:
            self.install_location_var.set(folderpath)

    def add_server_list_target(self):
        selected_tab_index = self.multi_url_notebook.index(self.multi_url_notebook.select())
        if selected_tab_index is None:
            messagebox.showwarning("No Source Selected", "Please select a source tab before adding a target.", parent=self)
            return
        
        widget_info = self.multi_url_widgets[selected_tab_index]
        target_tree = widget_info['target_tree']


        if not self.selected_program:
            return

        initial_dir = self.selected_program.get("InstallLocation")
        if not initial_dir or not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")

        filepath = filedialog.asksaveasfilename(
            title="Add Server List Target File",
            initialdir=initial_dir,
            initialfile="server.met",
            filetypes=[("All files", "*.*")]
        )
        if filepath:
            target_tree.insert("", tk.END, text=filepath)
            self.update_download_button_state() # Update download button state

    def remove_server_list_target(self):
        selected_tab_index = self.multi_url_notebook.index(self.multi_url_notebook.select())
        if selected_tab_index is None:
            messagebox.showwarning("No Source Selected", "Please select a source tab before removing a target.", parent=self)
            return
        
        widget_info = self.multi_url_widgets[selected_tab_index]
        target_tree = widget_info['target_tree']

        selected_items = target_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select a target path from the list to remove.", parent=self)
            return

        for item in selected_items:
            target_tree.delete(item)
        self.update_download_button_state() # Update download button state

    def on_target_tree_double_click(self, event):
        """Handle double-click on a target path to edit it."""
        if not self.is_editing:
            return # Only allow editing in edit mode
        
        tree = event.widget
        self._inline_edit_tree_item(tree, event)

    def browse_generic_target(self, target_var, default_filename):
        # This function is now only used for the single-file nodes.dat target
        initial_dir = self.selected_program.get("InstallLocation", os.path.expanduser("~"))
        filepath = filedialog.asksaveasfilename(
            title=f"Select Target Path for {default_filename}",
            initialdir=initial_dir, initialfile=default_filename, filetypes=[("All files", "*.*")]
        )
        if filepath:
            target_var.set(filepath)

    def _inline_edit_tree_item(self, tree, event):
        """Creates a temporary entry widget over a treeview item for editing."""
        item_id = tree.identify_row(event.y)
        if not item_id:
            return

        x, y, width, height = tree.bbox(item_id)
        original_path = tree.item(item_id, "text")
        entry_var = tk.StringVar(value=original_path)
        
        entry = ttk.Entry(tree, textvariable=entry_var)
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        def on_finish(event):
            new_path = entry_var.get()
            if new_path:
                tree.item(item_id, text=new_path)
            else: # If user deletes the path, remove the item
                tree.delete(item_id)
            entry.destroy()
            self.update_download_button_state() # Update button state

        entry.bind("<FocusOut>", on_finish)
        entry.bind("<Return>", on_finish)
        entry.bind("<Escape>", lambda e: entry.destroy())
        
    def download_server_list(self):
        if not self.selected_program:
            messagebox.showwarning("No Selection", "Please select a program first.")
            return

        # Gather all sources from the UI
        sources_to_download = {}
        for widgets in self.multi_url_widgets:
            url_or_name = widgets['url_var'].get()
            network_custom_lists = self._get_custom_lists_for_network(self.selected_program.get("Network"))
            combined_lists = {**self.EDONKEY_SERVER_LISTS, **network_custom_lists}
            # Resolve friendly name to URL if it exists, otherwise use the value as-is
            url = combined_lists.get(url_or_name, url_or_name)
            paths = [widgets['target_tree'].item(item, "text") for item in widgets['target_tree'].get_children()]

            # If no paths are defined, prompt the user for a save location.
            if url and not paths:
                self.log_message(f"No target path for {url}. Prompting for save location.")
                initial_dir = self.selected_program.get("InstallLocation", os.path.expanduser("~"))
                # Suggest a filename based on the URL
                suggested_filename = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url).path))
                filepath = filedialog.asksaveasfilename(
                    title=f"Save As...",
                    initialdir=initial_dir,
                    initialfile=suggested_filename,
                    filetypes=[("All files", "*.*")]
                )
                if filepath:
                    paths = [filepath]
                else:
                    self.log_message("Save cancelled by user.")
                    continue # Skip this source if user cancels

            if url and paths:
                sources_to_download[url] = paths

        # Handle special .reg file import if the virtual path is present
        for url, paths in sources_to_download.items():
            if "(Windows Registry)" in paths:
                # This is handled in _perform_multi_download now
                pass

        if not sources_to_download:
            messagebox.showwarning("No Sources", "There are no valid server list sources to download. Please add a source with a URL and at least one target path.", parent=self)
            return

        self.log_message(f"Starting multi-source server list download...")
        threading.Thread(target=self._perform_multi_download, args=(sources_to_download,), daemon=True).start()

    def add_multi_url_source(self):
        """Opens a dialog to add a new URL/path pair for multi-source mode."""
        dialog = tk.Toplevel(self)
        dialog.title("Add Source (URL or Local File)")
        dialog.geometry("450x150")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.grid_columnconfigure(1, weight=1)

        ttk.Label(frame, text="Source:").grid(row=0, column=0, sticky="w", pady=2)
        source_var = tk.StringVar()
        ttk.Entry(frame, textvariable=source_var).grid(row=0, column=1, sticky="ew", padx=5)

        def browse_local_file():
            filepath = filedialog.askopenfilename(
                title="Select Local Server File",
                filetypes=[("All files", "*.*")],
                parent=dialog
            )
            if filepath:
                # Convert to a file URI for consistent handling
                source_var.set(urllib.parse.urljoin('file:', urllib.request.pathname2url(filepath)))

        def on_ok():
            url = source_var.get()
            if not url:
                messagebox.showwarning("Missing Info", "A source URL or file path is required.", parent=dialog)
                return
            
            if url in self.selected_program['ServerListTargetPaths']:
                messagebox.showwarning("Duplicate Source", "This URL already exists as a source.", parent=dialog)
                return

            # Add to the internal data (with an empty list of paths) and refresh UI.
            if url not in self.selected_program['ServerListTargetPaths']:
                self.selected_program['ServerListTargetPaths'][url] = []
            self.display_details_panel(self.selected_program)
            dialog.destroy()
        
        ttk.Button(frame, text="Browse...", command=browse_local_file).grid(row=0, column=2, padx=(0, 5))

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=(15, 0), sticky='e')
        ttk.Button(button_frame, text="Add", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def add_custom_url(self):
        """Opens a dialog to add a new custom server URL."""
        if not self.selected_program:
            messagebox.showwarning("No Program Selected", "Please select a program first to associate the custom URL with its network.", parent=self)
            return
        network = self.selected_program.get("Network", "Unknown")

        dialog = tk.Toplevel(self)
        dialog.title("Add Custom Server URL")
        dialog.geometry("450x150")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        frame.grid_columnconfigure(1, weight=1)

        ttk.Label(frame, text="Friendly Name:").grid(row=0, column=0, sticky="w", pady=2)
        name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(frame, text="URL:").grid(row=1, column=0, sticky="w", pady=2)
        url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=url_var).grid(row=1, column=1, sticky="ew", padx=5)
        
        test_button = ttk.Button(frame, text="Test", command=lambda: self.test_url(url_var, parent=dialog))
        test_button.grid(row=1, column=2, padx=(0, 5))

        def on_ok():
            name = name_var.get().strip()
            url = url_var.get().strip() # This is the raw URL
            if not url:
                messagebox.showwarning("Missing Info", "A URL is required.", parent=dialog)
                return
            if not name: # If name is empty, use the URL as the name
                name = url
            
            network_custom_lists = self._get_custom_lists_for_network(network)
            if name in self.EDONKEY_SERVER_LISTS or name in network_custom_lists:
                messagebox.showwarning("Duplicate Name", "A server list with this name already exists.", parent=dialog)
                return

            network_custom_lists[name] = url
            self.save_settings()
            self.log_message(f"Added custom server URL '{name}' for the {network} network.")
            
            # Refresh the details panel to update the combobox values
            if self.selected_program:
                self.display_details_panel(self.selected_program)
            dialog.destroy()

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=(15, 0), sticky='e')
        ttk.Button(button_frame, text="Add", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def remove_custom_url(self):
        """Opens a dialog to remove a custom server URL."""
        if not self.selected_program:
            messagebox.showwarning("No Program Selected", "Please select a program to see its network's custom URLs.", parent=self)
            return
        network = self.selected_program.get("Network", "Unknown")
        network_custom_lists = self._get_custom_lists_for_network(network)

        if not network_custom_lists:
            messagebox.showinfo("No Custom URLs", f"There are no custom URLs to remove for the {network} network.", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title("Remove Custom Server URL")
        dialog.geometry("400x250")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Select a custom URL to remove:").pack(anchor='w', pady=(0, 5))

        listbox = tk.Listbox(frame)
        listbox.pack(fill=tk.BOTH, expand=True)
        for name in sorted(network_custom_lists.keys()):
            listbox.insert(tk.END, name)

        def on_ok():
            selection_indices = listbox.curselection()
            if not selection_indices:
                messagebox.showwarning("No Selection", "Please select a URL to remove.", parent=dialog)
                return

            name_to_remove = listbox.get(selection_indices[0])
            if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove '{name_to_remove}'?", parent=dialog):
                del network_custom_lists[name_to_remove]
                self.save_settings()
                self.log_message(f"Removed custom server URL '{name_to_remove}' from the {network} network.")
                self.display_details_panel(self.selected_program) # Refresh UI
                dialog.destroy()

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill='x', pady=(10, 0))
        ttk.Button(button_frame, text="Remove", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def remove_multi_url_source(self):
        """Removes the currently selected tab/source from the multi-URL notebook."""
        try:
            selected_tab_index = self.multi_url_notebook.index(self.multi_url_notebook.select())
        except tk.TclError:
            messagebox.showwarning("No Source Selected", "Please select a source tab to remove.", parent=self)
            return

        widget_info = self.multi_url_widgets[selected_tab_index]
        url_to_remove = widget_info['url_var'].get()
        del self.selected_program['ServerListTargetPaths'][url_to_remove]
        self.display_details_panel(self.selected_program) # Refresh UI

    def download_nodes_list(self):
        if not self.selected_program:
            messagebox.showwarning("No Selection", "Please select a program first.")
            return

        url = self.nodes_list_url_var.get()
        target_path = self.nodes_list_target_var.get()

        if not url:
            messagebox.showwarning("Missing URL", "Please enter a Nodes List URL.")
            return
        if not target_path:
            messagebox.showwarning("Missing Target Path", "Please specify a Nodes List Target Path.")
            return

        target_dir = os.path.dirname(target_path)
        if target_dir and not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except OSError as e:
                messagebox.showerror("Error", f"Could not create target directory '{target_dir}': {e}")
                return

        self.log_message(f"Attempting to download nodes list from: {url}")
        self.log_message(f"Saving to: {target_path}")
        threading.Thread(target=self._perform_download, args=(url, target_path, "NodesLastUpdated"), daemon=True).start()

    def download_winmx_patch(self):
        if not self.selected_program:
            messagebox.showwarning("No Selection", "Please select a program first.")
            return

        url = self.winmx_patch_url_var.get()
        target_path = self.winmx_patch_target_var.get()

        if not url or not target_path:
            messagebox.showwarning("Missing Information", "Both Patch URL and Target Path are required.", parent=self)
            return

        target_dir = os.path.dirname(target_path)
        if target_dir and not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except OSError as e:
                messagebox.showerror("Error", f"Could not create target directory '{target_dir}': {e}")
                return

        threading.Thread(target=self._perform_download, args=(url, target_path, "WinMXPatchLastUpdated", True), daemon=True).start()

    def _perform_reg_import(self, url):
        """Downloads a .reg file, saves it temporarily, and runs it."""
        temp_path = None
        try:
            self.after(0, self.log_message, f"Downloading .reg file from {url}...")
            # Download to a temporary file with a .reg extension
            temp_path, _ = urllib.request.urlretrieve(url)
            reg_file_path = temp_path + ".reg"
            shutil.move(temp_path, reg_file_path)
            temp_path = reg_file_path # Update temp_path to the new name

            self.after(0, self.log_message, f"Attempting to import registry file: {reg_file_path}")
            # Use 'reg import' which is silent and doesn't require user interaction
            # Using CREATE_NO_WINDOW to hide the command prompt
            process = subprocess.run(['reg', 'import', reg_file_path], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if process.returncode == 0:
                self.after(0, self.log_message, "SUCCESS: Registry file imported successfully.")
                self.after(0, messagebox.showinfo, "Import Complete", "Napigator server list has been imported successfully.")
            else:
                error_msg = f"FAILED to import registry file. Return code: {process.returncode}\nError: {process.stderr}"
                self.after(0, self.log_message, error_msg)
                self.after(0, messagebox.showerror, "Import Error", error_msg)
        except Exception as e:
            self.after(0, self.log_message, f"An unexpected error occurred during .reg import: {e}")
            self.after(0, messagebox.showerror, "Import Error", f"An unexpected error occurred: {e}")

    def _perform_multi_download(self, sources_to_download):
        """Downloads files from multiple sources to their respective targets."""
        success_count = 0
        fail_count = 0
        total_count = sum(len(paths) for paths in sources_to_download.values())

        for download_url, target_paths in sources_to_download.items():
            # Handle special .reg file import
            if "(Windows Registry)" in target_paths:
                self.after(0, self.log_message, f"Starting .reg file import from {download_url}...")
                # Run in the same thread to be part of the overall success/fail count
                self._perform_reg_import(download_url)
                continue # Move to the next source

            is_local_file = download_url.startswith('file:')
            temp_path = None
            try:
                if is_local_file:
                    # The "download_url" is a file URI. Convert it back to a system path.
                    local_path = urllib.request.url2pathname(urllib.parse.urlparse(download_url).path)
                    self.after(0, self.log_message, f"Copying from local file {local_path}...")
                    if not os.path.exists(local_path):
                        raise FileNotFoundError(f"Local source file not found: {local_path}")
                    temp_path = local_path # Use the local path directly for copying
                else:
                    # Download the file to a temporary location first
                    self.after(0, self.log_message, f"Downloading from {download_url}...")
                    temp_path, _ = urllib.request.urlretrieve(download_url)

                for target_path in target_paths:
                    try:
                        # Ensure target directory exists
                        target_dir = os.path.dirname(target_path)
                        if not os.path.exists(target_dir):
                            os.makedirs(target_dir, exist_ok=True)
                        # Copy the temp file to the final destination
                        shutil.copy(temp_path, target_path)
                        self.after(0, self.log_message, f"  -> Successfully copied to: {target_path}")
                        success_count += 1

                        # Show special message for .wsx files that require manual import
                        if target_path.lower().endswith(".wsx"):
                            self.after(0, messagebox.showinfo, "Manual Import Required",
                                       "The OpenNapster .WSX server list has been downloaded.\n\n"
                                       "This file must be manually imported into your client."
                                       )
                    except Exception as e:
                        self.after(0, self.log_message, f"  -> FAILED to copy to {target_path}: {e}")
                        fail_count += 1
            except Exception as e:
                action = "copy" if is_local_file else "download"
                self.after(0, self.log_message, f"FAILED to {action} from {download_url}: {e}")
                fail_count += len(target_paths) # All targets for this URL failed
            finally:
                if not is_local_file and temp_path and os.path.exists(temp_path):
                    os.remove(temp_path) # Clean up the temporary file

        self.after(0, self._on_multi_download_complete, success_count, fail_count, total_count)

    def _perform_download(self, url, target_path, last_updated_key="LastUpdated", show_popup=True):
        try:
            # Ensure target directory exists before download
            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            urllib.request.urlretrieve(url, target_path)
            
            # --- Update successful, now update the UI and save ---
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_type_map = {"NodesLastUpdated": "Nodes list", "LastUpdated": "Server list", "WinMXPatchLastUpdated": "WinMX patch"}
            file_type = file_type_map.get(last_updated_key, "File")

            
            def update_on_main_thread():
                if self.selected_program: # Check if program is still selected
                    self.selected_program[last_updated_key] = now_str
                    
                    # Only update the main "Last Updated" label if it's a server list
                    if last_updated_key == "LastUpdated":
                        self.last_updated_var.set(now_str)
                    elif last_updated_key == "NodesLastUpdated":
                        self.nodes_last_updated_var.set(now_str)
                    elif last_updated_key == "WinMXPatchLastUpdated":
                        self.winmx_patch_last_updated_var.set(now_str)

                    self.save_settings()
                self.log_message(f"Successfully downloaded {file_type.lower()} to: {target_path}")
                if show_popup:
                    messagebox.showinfo("Download Complete", f"{file_type} downloaded successfully to:\n{target_path}")

            self.after(0, update_on_main_thread)

        except urllib.error.URLError as e:
            file_type = file_type_map.get(last_updated_key, "File")
            error_message = f"Error downloading {file_type.lower()} from {url}: {e.reason}"
            self.after(0, self.log_message, error_message)
            if show_popup:
                self.after(0, messagebox.showerror, "Download Error", f"Could not download {file_type.lower()}:\n{e.reason}")
            raise e # Re-raise for multi-download to catch
        except Exception as e:
            error_message = f"An unexpected error occurred during {file_type.lower()} download: {e}"
            self.after(0, self.log_message, error_message)
            if show_popup:
                self.after(0, messagebox.showerror, "Download Error", f"An unexpected error occurred:\n{e}")
            raise e # Re-raise for multi-download to catch

    def _fetch_remote_update_times(self, program_info):
        """Starts threads to fetch the Last-Modified headers for relevant URLs."""
        # For server lists (multi-source)
        target_sources = program_info.get("ServerListTargetPaths", {})
        if target_sources:
            # We check the first URL. In most cases, all files in a multi-source set are updated together.
            first_url = next(iter(target_sources), None)
            if first_url:
                threading.Thread(target=self._get_last_modified, args=(first_url, self.remote_last_updated_var), daemon=True).start()
        else:
            self.remote_last_updated_var.set("N/A")

        # For nodes.dat
        nodes_url_or_name = program_info.get("NodesListURL")
        if nodes_url_or_name:
            nodes_url = self.EMULE_NODES_LISTS.get(nodes_url_or_name, nodes_url_or_name)
            threading.Thread(target=self._get_last_modified, args=(nodes_url, self.nodes_remote_last_updated_var), daemon=True).start()
        else:
            self.nodes_remote_last_updated_var.set("N/A")

        # For WinMX patch
        winmx_url = program_info.get("WinMXPatchURL")
        if winmx_url:
            threading.Thread(target=self._get_last_modified, args=(winmx_url, self.winmx_remote_last_updated_var), daemon=True).start()
        else:
            self.winmx_remote_last_updated_var.set("N/A")

    def _get_last_modified(self, url, result_var):
        """Worker thread to get the Last-Modified header from a URL."""
        try:
            # Use the GitHub API for raw.githubusercontent.com URLs for accurate timestamps
            if 'raw.githubusercontent.com' in url:
                self._get_github_last_modified(url, result_var)
                return

            # Do not attempt to make a web request for local file URIs.
            if url.startswith('file:'):
                self.after(0, result_var.set, "N/A")
                return

            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=10) as response:
                # Only use 'Last-Modified'. The 'Date' header is often the current time and misleading.
                last_modified = response.headers.get('Last-Modified')

                if last_modified:
                    # Try to parse the date and reformat it. If it fails for any reason, show N/A.
                    try:
                        dt = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S %Z')
                        self.after(0, result_var.set, dt.strftime('%Y-%m-%d %H:%M'))
                    except ValueError:
                        self.after(0, result_var.set, "N/A") # If format is unexpected, just show N/A
                else:
                    self.after(0, result_var.set, "N/A")
        except Exception:
            self.after(0, result_var.set, "N/A")

    def _get_github_last_modified(self, raw_url, result_var):
        """Fetches the last commit date for a file from raw.githubusercontent.com using the GitHub API."""
        try:
            # Example raw_url: https://raw.githubusercontent.com/USER/REPO/BRANCH/PATH/TO/FILE.txt
            parts = urllib.parse.urlparse(raw_url).path.split('/')
            if len(parts) < 5:
                self.after(0, result_var.set, "N/A")
                return

            user = parts[1]
            repo = parts[2]
            branch = parts[3]
            file_path = '/'.join(parts[4:])

            api_url = f"https://api.github.com/repos/{user}/{repo}/commits?path={file_path}&sha={branch}&per_page=1"

            # GitHub API requires a User-Agent header
            req = urllib.request.Request(api_url, headers={'User-Agent': 'P2P-Connection-Helper'})

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.load(response)
                if data:
                    # Date is in ISO 8601 format, e.g., "2023-10-27T18:30:00Z"
                    commit_date_str = data[0]['commit']['committer']['date']
                    # Parse ISO 8601 format and convert to local time for display
                    dt_utc = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
                    dt_local = dt_utc.astimezone(None)
                    self.after(0, result_var.set, dt_local.strftime('%Y-%m-%d %H:%M'))
                else:
                    self.after(0, result_var.set, "N/A")
        except Exception:
            # If API fails for any reason, fall back to N/A
            self.after(0, result_var.set, "N/A")

    def _on_multi_download_complete(self, success_count, fail_count, total_count):
        """Updates UI after a multi-target download is finished."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if success_count > 0:
            if self.selected_program: # Check if program is still selected
                self.selected_program["LastUpdated"] = now_str
                self.last_updated_var.set(now_str)
                self.save_settings()

        if fail_count == 0:
            messagebox.showinfo("Download Complete", f"Server list(s) successfully downloaded to {success_count} location(s).")
        else:
            messagebox.showwarning("Download Incomplete", f"Server list download finished.\n\nSuccessful: {success_count}\nFailed: {fail_count}")


    def open_config_folder(self):
        if not self.selected_program:
            messagebox.showwarning("No Selection", "Please select a program from the list first.")
            return

        install_location = self.selected_program.get("InstallLocation")
        if not install_location or not os.path.isdir(install_location):
            messagebox.showwarning("Folder Not Found", f"Installation folder not found for {self.selected_program['DisplayName']}.")
            return

        try:
            os.startfile(install_location) # Works on Windows
            self.log_message(f"Opened folder: {install_location}")
        except AttributeError:
            # Fallback for non-Windows systems (though this app is Windows-focused)
            try:
                subprocess.Popen(['xdg-open', install_location]) # Linux
            except FileNotFoundError:
                try:
                    subprocess.Popen(['open', install_location]) # macOS
                except FileNotFoundError:
                    messagebox.showerror("Error", "Could not open folder. Your OS might not be supported for this action.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")

    def test_url(self, url_var, parent=None, is_nodes_dat=False):
        """Tests if a given URL is reachable."""
        url_or_name = url_var.get()
        if not url_or_name:
            messagebox.showwarning("No URL", "There is no URL to test.", parent=parent or self)
            return

        # Resolve friendly name to URL
        url_to_test = url_or_name
        if self.selected_program:
            network = self.selected_program.get("Network")
            network_custom_lists = self._get_custom_lists_for_network(network)
            
            # Check all relevant lists for a friendly name match
            if is_nodes_dat:
                combined_lists = self.EMULE_NODES_LISTS
            else:
                combined_lists = {**self.EDONKEY_SERVER_LISTS, **network_custom_lists}
            
            url_to_test = combined_lists.get(url_or_name, url_or_name)

        self.log_message(f"Testing URL: {url_to_test}...")
        
        # Run the test in a separate thread to avoid blocking the GUI
        threading.Thread(target=self._perform_url_test, args=(url_to_test, parent or self), daemon=True).start()

    def _perform_url_test(self, url, parent):
        """Worker function to perform the URL HEAD request."""
        # Handle local file URIs
        if url.startswith('file:'):
            try:
                # Convert file URI to a system-specific path
                file_path = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
                if os.path.exists(file_path):
                    self.after(0, self.log_message, f"SUCCESS: Local file exists at '{file_path}'.")
                    self.after(0, messagebox.showinfo, "Test Successful", "Local file exists.", parent=parent)
                else:
                    self.after(0, self.log_message, f"FAILURE: Local file not found at '{file_path}'.")
                    self.after(0, messagebox.showerror, "Test Failed", "Local file not found.", parent=parent)
            except Exception as e:
                self.after(0, self.log_message, f"FAILURE: Invalid file path. Error: {e}")
                self.after(0, messagebox.showerror, "Test Failed", f"Could not test the file path.\n\nError: {e}", parent=parent)
            return
        try:
            # Use a HEAD request to check for existence without downloading the content
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.getcode()
                if 200 <= status < 300:
                    self.after(0, self.log_message, f"SUCCESS: URL is reachable (Status: {status}).")
                    self.after(0, messagebox.showinfo, "Test Successful", f"URL is reachable.\n\nStatus Code: {status}", parent=parent)
                else:
                    self.after(0, self.log_message, f"WARNING: URL returned status {status}.")
                    self.after(0, messagebox.showwarning, "Test Warning", f"URL returned a non-success status code: {status}", parent=parent)
        except Exception as e:
            self.after(0, self.log_message, f"FAILURE: Could not reach URL. Error: {e}")
            self.after(0, messagebox.showerror, "Test Failed", f"Could not reach the URL.\n\nError: {e}", parent=parent)

    def show_faq_window(self):
        """Creates and shows the Information & FAQ window."""
        # If window already exists, just bring it to the front
        if self.faq_window and self.faq_window.winfo_exists():
            self.faq_window.lift()
            return

        self.faq_window = tk.Toplevel(self)
        self.faq_window.title("Information & FAQ")
        self.faq_window.geometry("750x550")
        self.faq_window.transient(self)

        notebook = ttk.Notebook(self.faq_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create and add tabs with content
        self._create_faq_tab(notebook, "About This Program", self._get_about_program_text())
        self._create_faq_tab(notebook, "P2P Networks", self._get_networks_faq_text())
        self._create_faq_tab(notebook, "Clients & Servers", self._get_clients_servers_faq_text())
        self._create_faq_tab(notebook, "Supported Software", self._get_supported_software_text())

    def _create_faq_tab(self, notebook, title, text_content):
        """Helper function to create a tab with scrollable, read-only text."""
        tab_frame = ttk.Frame(notebook, padding=10)
        notebook.add(tab_frame, text=title)

        st = scrolledtext.ScrolledText(tab_frame, wrap=tk.WORD, font=("Segoe UI", 10))
        st.tag_configure("bold", font=("Segoe UI", 10, "bold"), foreground="#000080") # Use a navy blue for better visibility
        st.tag_configure("heading", font=("Segoe UI", 12, "bold"), spacing1=5, spacing3=5)
        st.tag_configure("bullet", lmargin1=20, lmargin2=20)
        st.pack(fill=tk.BOTH, expand=True)

        # Simple parser for markdown-like formatting
        for i, line in enumerate(text_content.split('\n')):
            # Check for headings (text followed by ---)
            if (i + 1) < len(text_content.split('\n')) and text_content.split('\n')[i+1].startswith('---'):
                st.insert(tk.END, line + '\n', "heading")
                continue
            if line.startswith('---'): # Skip the '---' line itself
                continue
            else:
                # Handle bolding within the line
                parts = re.split(r'(\*\*.*?\*\*)', line)
                for part in parts:
                    if part.startswith('**') and part.endswith('**'):
                        st.insert(tk.END, part[2:-2], "bold") # This handles explicit **bold** markdown
                    else:
                        st.insert(tk.END, part)
                
                # Handle bullet points by applying margin tags
                if line.strip().startswith('•'):
                    st.insert(tk.END, '\n', "bullet")
                else:
                    st.insert(tk.END, '\n')

        st.config(state=tk.DISABLED) # Make it read-only

    def _get_about_program_text(self):
        return f"""Disclaimer
----------
{self.DISCLAIMER_TEXT}

P2P Connection Helper
-------------------------
This program is designed to help you manage and maintain legacy peer-to-peer (P2P) file-sharing applications. Many of these older programs rely on server lists or network patches to connect to their respective networks, and these resources can become outdated or hard to find.

Key Features:

• Registry Scan: Automatically detects P2P clients installed on your system by scanning the Windows Registry.

• Manual Add: Allows you to add programs that were not detected automatically, such as portable applications.

• Server List Management: For networks like eDonkey and Gnutella, this tool can download and install updated server lists (e.g., `server.met`, `gnutella.net`) to the correct configuration folders.

• Connection Patches: For clients like WinMX, it can download necessary patches (e.g., `oledlg.dll`) that enable them to connect to modern community-run networks.

• Multi-Source Downloads: For clients like Morpheus and Gnucleus, it can download multiple required cache files from different URLs.

• Client & Server Downloads: Provides a curated list of links to download installers for various P2P clients and server applications.

• Link Testing: You can test if server list URLs are active before downloading. The "Client & Server Downloads" tab also has a feature to test all installer links.

• Launching: You can launch your P2P programs directly from the helper.

The goal is to provide a centralized place to keep these classic applications running smoothly."""

    def _get_networks_faq_text(self):
        return """What are P2P Networks?
-----------------------
A peer-to-peer (P2P) network is a system where individual computers (peers) connect with each other directly to share files, without needing a central server to mediate the transfer. This application supports several classic networks:

• Gnutella: Born in 2000, Gnutella was one of the first truly decentralized file-sharing networks. Early clients connected and discovered each other by "gossiping"—asking connected peers for the addresses of other peers. This simple but effective design led to its rapid adoption by clients like LimeWire, FrostWire, and BearShare. To connect today, clients use a "host cache" file (like `gnutella.net`) to find their initial connection points. It's important to note that the modern Gnutella network primarily supports protocol version 0.6, so very old clients that do not support this version may be unable to connect.

• eDonkey/Kadmille (eD2k): The eDonkey network, created in 2000, started as a hybrid system. It relied on central servers (listed in a `server.met` file) to index files and help clients find each other, but the files themselves were transferred directly between peers. To improve decentralization, the serverless Kademlia (Kad) network was later integrated. Modern clients like eMule use both systems simultaneously, connecting to servers for a quick start and using the robust Kad network for long-term stability.

• GnuCDNA/Gnutella2 (G2): Gnutella2 was created as an evolution of the original Gnutella protocol, designed to be more efficient. It introduced a "hub" and "leaf" system, where powerful computers act as hubs to manage search requests for many connected "leaf" clients. This reduced network traffic compared to Gnutella's original search method. Clients like Morpheus, Gnucleus, and Phex are primary users of the G2 network. A key feature of these clients is their backward compatibility; they can also connect to the original Gnutella network, allowing them to access a wider pool of users and files.

• OpenNapster: After the original Napster shut down, its server software was reverse-engineered, leading to the creation of OpenNap. This allowed anyone to run a Napster-compatible server, creating a decentralized network of community-run servers. Clients like the original Napster (with help from Napigator), WinMX, and XNap can connect to this network.

• WinMX: WinMX rose to prominence in the early 2000s as a highly popular P2P client, especially in Japan. It connected to its own centralized network, the WinMX Peer Network (WPN), which was known for its stability and large variety of files. Unlike many other networks, it also featured integrated chat rooms, fostering a strong sense of community. In 2005, following legal pressure, the official servers that powered the WPN were shut down, rendering the client unable to connect. However, the dedicated WinMX community refused to let it die. Developers and users worked together to create a "connection patch"—a modified `oledlg.dll` file. By replacing the original file with this patched version, users could bypass the need for official servers and connect to a new, decentralized network of community-operated servers, effectively resurrecting the network. Today, the patched WinMX client remains a versatile tool. It can connect to the revived WPN and is also capable of connecting to the OpenNapster network, often by manually importing a server list file (`.wsx`), allowing users to access two distinct P2P ecosystems from a single application.

• Ares: The Ares network, popularized by the Ares Galaxy client, was a decentralized network that gained significant traction in the mid-2000s. It was known for its very fast connection times, user-friendly interface, and built-in chat rooms. It used its own protocol and was initially a closed-source project, but later became open source. For a time, it was one of the most used P2P networks. Unfortunately, the network has since declined and is now considered **defunct** and no longer accessible.

• OpenFT: OpenFT (Open FastTrack) was a network created by reverse-engineering the FastTrack protocol, which was famously used by the original Kazaa, Grokster, and iMesh clients. The goal was to create an open-source alternative that was not controlled by a single company. Clients like giFT (and its frontends like KCeasy) could connect to it. Like the original FastTrack, it was a highly decentralized network. However, over time, its user base dwindled, and the network is now considered **defunct**."""

    def _get_clients_servers_faq_text(self):
        return """What are Clients and Servers?
-----------------------------
• Client: A "client" is the software application you run on your computer to connect to a P2P network. Examples include eMule, LimeWire, WinMX, and Morpheus. The client is your interface for searching for, downloading, and sharing files.

• Server (in the context of P2P): The role of a "server" depends on the network:

  • eDonkey Network: Servers are central points that clients connect to. They don't store files themselves, but they keep a list of which files are being shared by the connected clients. When you search, you are asking the server for a list of clients who have the file you want. The `server.met` file is a list of these servers.

  • OpenNapster Network: Similar to eDonkey, these servers act as indexes for files and help clients find each other.

  • Gnutella/G2 Networks: These networks are mostly "serverless," but they use "host caches" or "web caches." These are simple files, often hosted on a web server, that contain a list of IP addresses of other peers. A client downloads this list to find its first connections to the network.

• Server Application: This is different from a P2P server. A server application (like SlavaNap or GWC Server) is a program you can run to become a server for a network like OpenNapster or Gnutella. This is for advanced users who want to help support the network infrastructure."""

    def _get_supported_software_text(self):
        """Generates the text for the 'Supported Software' FAQ tab."""
        
        # Descriptions for each client and server
        descriptions = {
            "Cabos": "An open-source Gnutella client based on LimeWire and Acquisition. It is known for its simple interface and can also connect to the Gnutella2 (G2) network.",
            "DexterWire": "A Gnutella client based on the LimeWire source code.", # No star here
            "FileNavigator": "A client for the OpenNapster network that uses a .reg file to import server lists, similar to Napigator.",
            "Swaptor": "A client for the OpenNapster network, based on FileNavigator. It uses a .reg file to import server lists.",
            "BearShare": "A classic client that connects to the Gnutella2 (G2) network.",
            "KCeasy": "A multi-network client that uses the giFT backend. It can connect to the Gnutella and Gnutella2 (G2) networks. While it previously supported other networks like Ares and OpenFT, these are no longer functional.",
            "FrostWire": "A popular Gnutella client, originally a fork of LimeWire.",
            "LimeWire": "One of the most well-known Gnutella clients.",
            "LemonWire": "A Gnutella client based on the LimeWire source code.",
            "TurboWire": "A Gnutella client based on the LimeWire source code.",
            "LuckyWire": "A Gnutella client based on the LimeWire source code.",
            "WireShare": "A fork of LimeWire, providing another alternative for the Gnutella network.",
            "XNap": "A versatile client written in Java that can connect to multiple networks, including Gnutella and OpenNapster.",
            "WinMX": "A classic client that connects to its own community network and can also access OpenNapster servers.",
            "Phex": "An open-source Gnutella2 (G2) client known for its advanced features.",
            "Napster": "The original client that started the P2P revolution. It requires a tool like Napigator to find and connect to modern OpenNapster servers.",
            "Napigator": "Originally for the classic Napster client, this utility now finds and manages servers for the OpenNapster network, allowing legacy clients to connect.",
            "MyNapster": "A client for the Gnutella2 (G2) network.",
            "Morpheus": "A well-known client for the Gnutella2 (G2) network.",
            "NeoNapster": "A client for the Gnutella2 (G2) network, similar in function to XoloX and Gnucleus.",
            "XoloX": "A client for the Gnutella2 (G2) network, similar in function to Gnucleus.",
            "Gnucleus": "One of the original clients for the Gnutella2 (G2) network.",
            "eMule": "The most popular client for the eDonkey/Kadmille network, known for its large user base and features.",
            "Lphant": "A client for the eDonkey/Kadmille network, similar to eMule.",
            "eDonkey 2000": "The original client for the eDonkey network.",
            "SlavaNap Server": "A server application for hosting an OpenNapster-compatible server.",
            "phpgnucacheii server": "A web-based Gnutella web cache server written in PHP.",
            "OpenNap server": "An open-source server for the OpenNapster network.",
            "GWebCache Server": "A server application for providing a Gnutella web cache.",
            "GWC Server": "A server application for providing a Gnutella web cache.",
            "Red Flags Server": "A server application for providing a Gnutella web cache.",
            "Cachechu Server": "A server application for providing a Gnutella web cache.",
            "Beacon Server": "A server application for providing a Gnutella web cache.",
            "Beacon1 Server": "A server application for providing a Gnutella web cache.",
            "Beacon2 Server": "A server application for providing a Gnutella web cache.",
        }

        text = "Clients\n-------------------------\n"
        server_names = [s for s in self.CLIENT_DOWNLOADS if "server" in s.lower()]
        
        # Sort and add clients
        for name in sorted(self.CLIENT_DOWNLOADS.keys()):
            if name not in server_names:
                desc = descriptions.get(name, "A peer-to-peer file sharing application.")
                text += f"• **{name}**: {desc}\n"

        text += "\nOther Notable Clients (Not available for download here)\n-------------------------\n"

        text += "\nServer Applications\n-------------------------\n"
        # Sort and add servers
        for name in sorted(server_names):
            desc = descriptions.get(name, "A server application for a P2P network.")
            text += f"• **{name}**: {desc}\n"
            
        return text

    def show_about_dialog(self):
        """Displays the about dialog box."""
        about_text = f"""P2P Connection Helper v{self.VERSION}

A utility to help manage and update server lists for legacy P2P applications.

--- Disclaimer ---
{self.DISCLAIMER_TEXT}"""
        messagebox.showinfo(f"About P2P Connection Helper v{self.VERSION}", about_text, parent=self)

    def reset_settings(self):
        """Deletes the settings file and restarts the application."""
        if messagebox.askyesno("Reset Settings?",
                               "This will delete all saved settings, including manually added programs and custom URLs, and restart the application.\n\nAre you sure you want to continue?",
                               icon='warning', parent=self):
            try:
                if os.path.exists(self.settings_file):
                    os.remove(self.settings_file)
                    self.log_message(f"Settings file '{self.settings_file}' deleted.")
                else:
                    self.log_message("No settings file to delete.")

                self.log_message("Restarting application...")
                # Use Popen for a more reliable restart, especially when elevated.
                # It correctly handles the working directory.
                args = [sys.executable] + sys.argv
                subprocess.Popen(args, cwd=self.script_dir)
                self.quit() # Close the current instance

            except Exception as e:
                error_msg = f"Failed to reset settings and restart: {e}"
                self.log_message(error_msg)
                messagebox.showerror("Reset Error", error_msg, parent=self)

    def show_startup_disclaimer(self):
        """Shows a startup disclaimer window if not disabled in settings."""
        if not self.settings.get("show_disclaimer", True):
            return

        dialog = tk.Toplevel(self)
        dialog.title("Disclaimer")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Set the same icon as the main window
        try:
            icon_path = os.path.join(self.script_dir, "p2p.ico")
            if os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass # Ignore if icon setting fails

        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=self.DISCLAIMER_TEXT, justify=tk.LEFT, wraplength=400).pack(pady=(0, 15))

        dont_show_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Do not show this message again", variable=dont_show_var).pack(anchor='w', pady=(0, 10))

        def on_ok():
            if dont_show_var.get():
                self.settings["show_disclaimer"] = False
                self.save_settings()
            dialog.destroy()

        ok_button = ttk.Button(frame, text="OK", command=on_ok)
        ok_button.pack()

        # Center the dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

    def show_bearshare_test_warning(self):
        """Shows a startup warning if BearShare Test is detected."""
        if not self.settings.get("show_bearshare_test_warning", True):
            return

        is_bst_present = any(
            'bearshare test' in p.get("DisplayName", "").lower()
            for p in self.installed_programs
        )

        if not is_bst_present:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Important: BearShare Test Detected")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        try:
            icon_path = os.path.join(self.script_dir, "p2p.ico")
            if os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass

        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        warning_text = (
            "You have 'BearShare Test' in your program list. This is an old beta version with an expiration date and will not run normally.\n\n"
            "To use it, you must run it with a tool like **RunAsDate**.\n\n"
            "Set the date and time in RunAsDate to:\n"
            "**25.07.2005 at 12:00**\n\n"
            "You can also have RunAsDate create a desktop shortcut and then point the 'Executable Path' for BearShare Test in this program to that new shortcut file."
        )
        ttk.Label(frame, text=warning_text, justify=tk.LEFT, wraplength=450).pack(pady=(0, 15))

        dont_show_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Do not show this message again", variable=dont_show_var).pack(anchor='w', pady=(0, 10))

        def on_ok():
            if dont_show_var.get():
                self.settings["show_bearshare_test_warning"] = False
                self.save_settings()
            dialog.destroy()

        ok_button = ttk.Button(frame, text="OK", command=on_ok)
        ok_button.pack()

def is_admin():
    """Check if the script is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def set_window_app_id(tk_window):
    """
    Forcefully sets the AppUserModelID on a specific tkinter window handle (HWND).
    This is a robust way to ensure the correct taskbar icon is used on Windows.
    """
    if not (ctypes and hasattr(ctypes, 'windll') and hasattr(ctypes.windll, 'shell32')):
        return

    # Define necessary structures and constants
    try:
        from ctypes import wintypes

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [
                ('fmtid', wintypes.GUID),
                ('pid', wintypes.DWORD)
            ]

        class PROPVARIANT(ctypes.Structure):
            _fields_ = [
                ('vt', wintypes.USHORT),
                ('reserved1', wintypes.USHORT),
                ('reserved2', wintypes.USHORT),
                ('reserved3', wintypes.USHORT),
                ('pszVal', wintypes.LPWSTR),
                ('reserved4', ctypes.c_ulonglong)
            ]

        PKEY_AppUserModel_ID = PROPERTYKEY(wintypes.GUID('{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}'), 5)
        myappid = f'mycompany.p2phelper.v{P2PHelperApp.VERSION}'
        
        # Get the window handle (HWND) directly. Using winfo_pathname is the most reliable way for tkinter.
        hwnd = tk_window.winfo_id()

        pv = PROPVARIANT()
        pv.vt = 31  # VT_LPWSTR
        pv.pszVal = myappid
        ctypes.windll.shell32.SHSetWindowProperty(hwnd, ctypes.byref(PKEY_AppUserModel_ID), ctypes.byref(pv))
    except Exception as e:
        print(f"Warning: Could not set window AppUserModelID: {e}")

def main():
    # Set the AppUserModelID for the process *before* creating any windows.
    # This is crucial for the taskbar icon to be correct from the start.
    if ctypes and hasattr(ctypes, 'windll') and hasattr(ctypes.windll, 'shell32'):
        myappid = f'mycompany.p2phelper.v{P2PHelperApp.VERSION}'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    """Main function to handle UAC elevation."""

    # This function now handles the full elevation and application lifecycle.
    try:
        # If the script is not running as an admin, we attempt to relaunch it with elevation.
        if not is_admin():
            # The 'run_as_admin' function will show the UAC prompt.
            # We pass 'wait=True' to make the current (non-admin) process wait for the
            # elevated process to finish. This is the key to associating the taskbar icon correctly.
            return_code = run_as_admin(wait=True)

            # A return code of 1223 (ERROR_CANCELLED) means the user clicked "No" on the UAC prompt.
            # A return code of 0 means the elevated process ran and exited successfully.
            # Any other code is an error from the child process.
            if return_code == 1223: # ERROR_CANCELLED
                # We can inform the user and then proceed to run the app with limited rights.
                # This is better than just exiting.
                messagebox.showwarning("Admin Rights Not Granted",
                                       "The application will continue without administrator privileges.\n\n"
                                       "Some features, like modifying files in 'Program Files', may not work correctly.")
            # If the user approved UAC, the elevated process will run and this non-admin
            # process will simply wait here until it's closed, then exit.
            # We exit with the code from the child process.
            sys.exit(0) # Exit the non-admin process cleanly.
        
        # --- This code will only be reached by the elevated process (or if admin is not needed) ---

        # Show a warning if the optional 'Pillow' library is not installed.
        if not PIL_AVAILABLE:
            messagebox.showwarning("Optional Dependency Missing",
                                   "The 'Pillow' library was not found.\n\nProgram icons will not be displayed. To enable icons, please install it by running:\npip install Pillow")
        
        # Create and run the main application window.
        app = P2PHelperApp()
        # Schedule the window-specific AppUserModelID call after the window is fully initialized.
        # This reinforces the icon association and sets the window icon.
        # It's important to set the AUMID before setting the icon for best results.
        icon_path = os.path.join(app.script_dir, "p2p.ico")
        if os.path.exists(icon_path):
            app.iconbitmap(icon_path)
        app.after_idle(lambda: set_window_app_id(app))

        app.mainloop()
    except Exception as e:
        # Log the exception to a file for debugging, as the GUI may not be available.
        error_log_file = "p2p_helper_error.log"
        with open(error_log_file, "a") as f:
            f.write(f"--- Startup Error: {e} ---\n")
            f.write(traceback.format_exc())
            f.write("\n")
        messagebox.showerror("Fatal Startup Error", f"The application failed to start: {e}\n\nCheck 'p2p_helper_error.log' for details.")
        sys.exit(1) # Exit with an error code

def run_as_admin(wait=False):
    """
    Re-run the script with administrator privileges using ShellExecuteExW
    to allow waiting for the new process to complete.
    """
    if not (ctypes and hasattr(ctypes, 'windll') and hasattr(ctypes.windll, 'shell32')):
        return -1 # Cannot elevate on non-Windows or if ctypes is missing

    # --- Key Change for Taskbar Icon ---
    # We must use 'pythonw.exe' for the elevated process.
    # 'python.exe' is a console application, and Windows will often group the
    # taskbar icon with the parent console, ignoring the AppUserModelID.
    # 'pythonw.exe' is a windowed application, which forces Windows to treat
    # it as a separate GUI process and correctly apply the icon.
    python_exe_path = os.path.dirname(sys.executable)
    pythonw_exe = os.path.join(python_exe_path, 'pythonw.exe')
    # Fallback to python.exe if pythonw.exe is not found (e.g., in some venvs)
    executable_to_run = pythonw_exe if os.path.exists(pythonw_exe) else sys.executable

    # Define necessary structures and constants from the Windows API
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    INFINITE = -1

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong),
            ("hIcon", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    try:
        params = " ".join(f'"{arg}"' for arg in sys.argv)
        
        proc_info = SHELLEXECUTEINFO()
        proc_info.cbSize = ctypes.sizeof(proc_info)
        proc_info.fMask = SEE_MASK_NOCLOSEPROCESS if wait else 0
        proc_info.lpVerb = "runas"
        proc_info.lpFile = executable_to_run
        proc_info.lpParameters = params
        proc_info.nShow = 1  # SW_SHOWNORMAL

        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(proc_info)):
            # If ShellExecuteExW fails, it returns 0. GetLastError gives the reason.
            return ctypes.windll.kernel32.GetLastError()

        if wait:
            ctypes.windll.kernel32.WaitForSingleObject(proc_info.hProcess, INFINITE)
            ctypes.windll.kernel32.CloseHandle(proc_info.hProcess)

        return 0 # Success
    except Exception as e:
        print(f"Failed to elevate privileges: {e}")
        return -1 # Indicate a general failure

if __name__ == "__main__":
    # On Windows, run the main function which handles elevation.
    # On other OSes where ctypes is None, it will also run main, which will
    # then just start the app without elevation logic.
    main()
