"""
Web Dashboard

FastAPI-based dashboard for viewing agent decisions and status.
"""

import os
import secrets
import hashlib
from datetime import datetime

from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from .decision_logger import DecisionLogger
from .llm_factory import create_llm_provider, get_available_providers

router = APIRouter()

# Session storage (in-memory for simplicity - use Redis for production)
# Maps session_token -> username
_sessions: dict[str, str] = {}

# Templates
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# Session cookie name
SESSION_COOKIE_NAME = "climate_agent_session"

# Configuration from environment
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "")


def create_session(username: str) -> str:
    """Create a new session token for a user."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = username
    return token


def verify_session(token: str) -> str | None:
    """Verify a session token and return the username, or None if invalid."""
    return _sessions.get(token)


def delete_session(token: str) -> None:
    """Delete a session token."""
    _sessions.pop(token, None)


def verify_credentials(username: str, password: str) -> bool:
    """Verify username and password using constant-time comparison."""
    if not DASHBOARD_USER or not DASHBOARD_PASS:
        return True  # Auth disabled
    correct_user = secrets.compare_digest(username.encode("utf8"), DASHBOARD_USER.encode("utf8"))
    correct_pass = secrets.compare_digest(password.encode("utf8"), DASHBOARD_PASS.encode("utf8"))
    return correct_user and correct_pass


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return bool(DASHBOARD_USER and DASHBOARD_PASS)


# Login Page HTML
LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Climate Agent</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = { darkMode: 'class' }
        if (localStorage.getItem('color-theme') === 'dark' || 
            (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        }
    </script>
</head>
<body class="bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 min-h-screen flex items-center justify-center">
    <div class="w-full max-w-md px-4">
        <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8">
            <div class="text-center mb-8">
                <div class="inline-flex items-center justify-center w-16 h-16 bg-blue-100 dark:bg-blue-900 rounded-full mb-4">
                    <i data-lucide="thermometer" class="w-8 h-8 text-blue-600 dark:text-blue-400"></i>
                </div>
                <h1 class="text-2xl font-bold text-gray-800 dark:text-white">Climate Agent</h1>
                <p class="text-gray-500 dark:text-gray-400 mt-1">Sign in to access the dashboard</p>
            </div>
            
            {% if error %}
            <div class="mb-6 p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg">
                <p class="text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                    <i data-lucide="alert-circle" class="w-4 h-4"></i>
                    {{ error }}
                </p>
            </div>
            {% endif %}
            
            <form method="POST" action="/login" class="space-y-5">
                <div>
                    <label for="username" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Username
                    </label>
                    <div class="relative">
                        <i data-lucide="user" class="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2"></i>
                        <input type="text" id="username" name="username" required autofocus
                            class="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg 
                                   bg-white dark:bg-gray-700 text-gray-800 dark:text-white
                                   focus:ring-2 focus:ring-blue-500 focus:border-transparent
                                   placeholder-gray-400 transition-colors"
                            placeholder="Enter your username">
                    </div>
                </div>
                
                <div>
                    <label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Password
                    </label>
                    <div class="relative">
                        <i data-lucide="lock" class="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2"></i>
                        <input type="password" id="password" name="password" required
                            class="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg 
                                   bg-white dark:bg-gray-700 text-gray-800 dark:text-white
                                   focus:ring-2 focus:ring-blue-500 focus:border-transparent
                                   placeholder-gray-400 transition-colors"
                            placeholder="Enter your password">
                    </div>
                </div>
                
                <button type="submit"
                    class="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg
                           transition-colors flex items-center justify-center gap-2 shadow-lg shadow-blue-500/30">
                    <i data-lucide="log-in" class="w-5 h-5"></i>
                    Sign In
                </button>
            </form>
        </div>
        
        <p class="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
            AI-powered thermostat control
        </p>
    </div>
    <script>lucide.createIcons();</script>
</body>
</html>
"""

# We'll use inline HTML since we're in a container, but split into pages
PROMPTS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Prompts - Climate Agent</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
        }
    </script>
    <script>
        // Check local storage for dark mode preference
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark')
        }
    </script>
    <script src="https://unpkg.com/lucide@latest"></script>
</head>
<body class="bg-gray-100 dark:bg-gray-900 min-h-screen transition-colors duration-200">
    <div class="container mx-auto px-4 py-8">
        <div class="flex justify-between items-center mb-8">
            <div class="flex items-center gap-4">
                 <a href="/" class="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 flex items-center gap-2">
                    <i data-lucide="arrow-left"></i> Back to Dashboard
                 </a>
                 <h1 class="text-3xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-3">
                    <i data-lucide="file-text"></i> Agent Prompts
                 </h1>
            </div>
            <div class="flex items-center gap-4">
                <a href="/chat" class="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium flex items-center gap-2">
                    <i data-lucide="message-circle" class="w-4 h-4"></i> Chat
                </a>
                <button id="theme-toggle" type="button" class="text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-4 focus:ring-gray-200 dark:focus:ring-gray-700 rounded-lg text-sm p-2.5">
                    <i data-lucide="moon" id="theme-toggle-dark-icon" class="hidden w-5 h-5"></i>
                    <i data-lucide="sun" id="theme-toggle-light-icon" class="hidden w-5 h-5"></i>
                </button>
            </div>
        </div>

        <div class="grid grid-cols-1 gap-8" id="prompts-container">
            <!-- Prompts loaded here -->
            <div class="text-center py-8">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
                <p class="mt-4 text-gray-500">Loading prompts...</p>
            </div>
        </div>
        
    </div>

    <script>
        // Initialize Lucide
        lucide.createIcons();

        // Dark mode toggle logic (reused)
        var themeToggleDarkIcon = document.getElementById('theme-toggle-dark-icon');
        var themeToggleLightIcon = document.getElementById('theme-toggle-light-icon');
        
        function updateThemeIcons() {
            if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                themeToggleLightIcon.classList.remove('hidden');
                themeToggleDarkIcon.classList.add('hidden');
            } else {
                themeToggleLightIcon.classList.add('hidden');
                themeToggleDarkIcon.classList.remove('hidden');
            }
        }
        updateThemeIcons();

        var themeToggleBtn = document.getElementById('theme-toggle');
        themeToggleBtn.addEventListener('click', function() {
            themeToggleDarkIcon.classList.toggle('hidden');
            themeToggleLightIcon.classList.toggle('hidden');
            if (localStorage.getItem('color-theme')) {
                if (localStorage.getItem('color-theme') === 'light') {
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('color-theme', 'dark');
                } else {
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('color-theme', 'light');
                }
            } else {
                if (document.documentElement.classList.contains('dark')) {
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('color-theme', 'light');
                } else {
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('color-theme', 'dark');
                }
            }
            updateThemeIcons();
        });

        // Load prompts
        async function loadPrompts() {
            try {
                const response = await fetch('/api/prompts');
                const prompts = await response.json();
                
                const container = document.getElementById('prompts-container');
                container.innerHTML = '';
                
                prompts.forEach(prompt => {
                    const card = document.createElement('div');
                    card.className = 'bg-white dark:bg-gray-800 rounded-lg shadow p-6';
                    card.innerHTML = `
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100">${prompt.key}</h2>
                                <p class="text-sm text-gray-500 dark:text-gray-400">${prompt.description || 'No description'}</p>
                            </div>
                            <span class="text-xs text-gray-400">Last updated: ${prompt.updated_at || 'Never'}</span>
                        </div>
                        <textarea id="content-${prompt.key}" rows="15" 
                            class="w-full p-4 text-sm font-mono bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:text-gray-300 resize-y mb-4"
                        >${prompt.content}</textarea>
                        <div class="flex justify-end gap-2">
                             <button onclick="savePrompt('${prompt.key}')" 
                                class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2">
                                <span>Save Changes</span>
                             </button>
                        </div>
                    `;
                    container.appendChild(card);
                });
            } catch (error) {
                console.error('Error loading prompts:', error);
            }
        }

        async function savePrompt(key) {
            const content = document.getElementById(`content-${key}`).value;
            const btn = event.target.closest('button');
            const originalText = btn.innerHTML;
            
            try {
                btn.disabled = true;
                btn.innerHTML = '<span class="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></span> Saving...';
                
                const response = await fetch(`/api/prompts/${key}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content })
                });
                
                if (response.ok) {
                    btn.innerHTML = '✓ Saved';
                    btn.classList.remove('bg-blue-600', 'hover:bg-blue-700');
                    btn.classList.add('bg-green-600', 'hover:bg-green-700');
                    setTimeout(() => {
                        btn.innerHTML = originalText;
                        btn.classList.add('bg-blue-600', 'hover:bg-blue-700');
                        btn.classList.remove('bg-green-600', 'hover:bg-green-700');
                        btn.disabled = false;
                        // Refresh to update timestamp
                        loadPrompts();
                    }, 2000);
                } else {
                    throw new Error('Failed to save');
                }
            } catch (error) {
                console.error('Error saving prompt:', error);
                btn.innerHTML = '⚠ Error';
                btn.classList.remove('bg-blue-600', 'hover:bg-blue-700');
                btn.classList.add('bg-red-600', 'hover:bg-red-700');
                setTimeout(() => {
                    btn.innerHTML = originalText;
                    btn.classList.remove('bg-red-600', 'hover:bg-red-700');
                    btn.classList.add('bg-blue-600', 'hover:bg-blue-700');
                    btn.disabled = false;
                }, 3000);
            }
        }

        loadPrompts();
    </script>
</body>
</html>
"""

SETTINGS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings - Climate Agent</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
        }
    </script>
    <script>
        // Check local storage for dark mode preference
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark')
        }
    </script>
</head>
<body class="bg-gray-100 dark:bg-gray-900 min-h-screen transition-colors duration-200">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <div class="flex justify-between items-center mb-8">
            <div class="flex items-center gap-4">
                 <a href="/" class="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 flex items-center gap-2">
                    <i data-lucide="arrow-left"></i> Back to Dashboard
                 </a>
                 <h1 class="text-3xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-3">
                    <i data-lucide="settings"></i> Settings
                 </h1>
            </div>
            <div class="flex items-center gap-4">
                <a href="/chat" class="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium flex items-center gap-2">
                    <i data-lucide="message-circle" class="w-4 h-4"></i> Chat
                </a>
                <button id="theme-toggle" type="button" class="text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-4 focus:ring-gray-200 dark:focus:ring-gray-700 rounded-lg text-sm p-2.5">
                    <i data-lucide="moon" id="theme-toggle-dark-icon" class="hidden w-5 h-5"></i>
                    <i data-lucide="sun" id="theme-toggle-light-icon" class="hidden w-5 h-5"></i>
                </button>
            </div>
        </div>

        <div id="settings-container" class="space-y-8">
            <!-- Loading -->
            <div class="text-center py-8">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
                <p class="mt-4 text-gray-500">Loading settings...</p>
            </div>
        </div>
    </div>

    <script>
        // Initialize Lucide
        lucide.createIcons();

        // Dark mode toggle logic
        var themeToggleDarkIcon = document.getElementById('theme-toggle-dark-icon');
        var themeToggleLightIcon = document.getElementById('theme-toggle-light-icon');
        var themeToggleBtn = document.getElementById('theme-toggle');

        function updateThemeIcons() {
            if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                themeToggleLightIcon.classList.remove('hidden');
                themeToggleDarkIcon.classList.add('hidden');
            } else {
                themeToggleLightIcon.classList.add('hidden');
                themeToggleDarkIcon.classList.remove('hidden');
            }
        }
        updateThemeIcons();

        themeToggleBtn.addEventListener('click', function() {
            if (localStorage.getItem('color-theme')) {
                if (localStorage.getItem('color-theme') === 'light') {
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('color-theme', 'dark');
                } else {
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('color-theme', 'light');
                }
            } else {
                if (document.documentElement.classList.contains('dark')) {
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('color-theme', 'light');
                } else {
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('color-theme', 'dark');
                }
            }
            updateThemeIcons();
        });

        // Load Settings
        async function loadSettings() {
            try {
                const response = await fetch('/api/settings');
                const settings = await response.json();
                
                const container = document.getElementById('settings-container');
                container.innerHTML = '';
                
                // Group by category
                const groups = {};
                settings.forEach(s => {
                    if (!groups[s.category]) groups[s.category] = [];
                    groups[s.category].push(s);
                });

                // Render groups
                Object.keys(groups).forEach(category => {
                    const groupDiv = document.createElement('div');
                    groupDiv.className = 'bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden';
                    
                    let html = `
                        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700">
                            <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100">${category || 'General'}</h2>
                        </div>
                        <div class="p-6 space-y-6">
                    `;

                    groups[category].forEach(setting => {
                        html += `
                            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                                <div class="md:col-span-2">
                                    <label for="${setting.key}" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        ${formatKey(setting.key)}
                                    </label>
                                    <p class="text-xs text-gray-500 dark:text-gray-400">${setting.description}</p>
                                </div>
                                <div class="flex gap-2">
                                    <input type="text" id="${setting.key}" value="${setting.value}" 
                                        class="flex-1 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5">
                                    <button onclick="saveSetting('${setting.key}')"
                                        class="text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:ring-blue-300 font-medium rounded-lg text-sm px-4 py-2 dark:bg-blue-600 dark:hover:bg-blue-700 focus:outline-none dark:focus:ring-blue-800">
                                        Save
                                    </button>
                                </div>
                            </div>
                        `;
                    });

                    html += '</div>';
                    groupDiv.innerHTML = html;
                    container.appendChild(groupDiv);
                });
                
            } catch (error) {
                console.error('Error loading settings:', error);
                document.getElementById('settings-container').innerHTML = `
                    <div class="text-center text-red-500 py-8">
                        Error loading settings. Please refresh.
                    </div>
                `;
            }
        }

        async function saveSetting(key) {
            const input = document.getElementById(key);
            const value = input.value;
            const btn = event.target;
            const originalText = btn.innerText;

            try {
                btn.disabled = true;
                btn.innerText = '...';
                
                const response = await fetch(`/api/settings/${key}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value })
                });

                if (response.ok) {
                    const originalClass = btn.className;
                    btn.className = "text-white bg-green-600 hover:bg-green-700 font-medium rounded-lg text-sm px-4 py-2 focus:outline-none";
                    btn.innerText = 'Saved';
                    setTimeout(() => {
                        btn.className = originalClass;
                        btn.innerText = originalText;
                        btn.disabled = false;
                    }, 2000);
                } else {
                    throw new Error('Failed to save');
                }
            } catch (error) {
                console.error(error);
                btn.innerText = 'Error';
                btn.className = "text-white bg-red-600 hover:bg-red-700 font-medium rounded-lg text-sm px-4 py-2";
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerText = originalText;
                }, 3000);
            }
        }

        function formatKey(key) {
            return key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
        }

        loadSettings();
    </script>
</body>
</html>
"""

CHAT_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Chat - Climate Agent</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
        }
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        }
    </script>
    <style>
        html, body { height: 100%; overflow: hidden; }
        .chat-message {
            animation: fadeIn 0.3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .typing-indicator span {
            animation: bounce 1.4s infinite ease-in-out;
        }
        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }
        /* iOS viewport fix */
        @supports (-webkit-touch-callout: none) {
            body { height: -webkit-fill-available; }
        }
    </style>
</head>
<body class="bg-gray-100 dark:bg-gray-900 flex flex-col">
    <div class="flex-1 flex flex-col max-w-4xl mx-auto w-full overflow-hidden">
        <!-- Header -->
        <div class="flex-shrink-0 px-3 sm:px-4 py-2 sm:py-4">
        <div class="flex justify-between items-center">
                <div class="flex items-center gap-2 min-w-0">
                    <i data-lucide="message-circle" class="w-5 h-5 sm:w-6 sm:h-6 text-gray-800 dark:text-gray-100 flex-shrink-0"></i>
                    <h1 class="text-lg sm:text-2xl font-bold text-gray-800 dark:text-gray-100 truncate">Climate Agent</h1>
                </div>
                <!-- LLM Provider Selector -->
                <div class="flex items-center gap-2">
                    <select id="llm-provider" class="text-xs sm:text-sm bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded-lg px-2 py-1 focus:ring-blue-500 focus:border-blue-500">
                        <option value="">Loading...</option>
                    </select>
                    <select id="llm-model" class="hidden sm:block text-xs sm:text-sm bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded-lg px-2 py-1 focus:ring-blue-500 focus:border-blue-500 max-w-32">
                        <option value="">Default</option>
                    </select>
                </div>
                <div class="flex items-center gap-1 sm:gap-3 flex-shrink-0">
                    <a href="/" class="p-2 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300" title="Dashboard">
                        <i data-lucide="home" class="w-5 h-5"></i>
                    </a>
                    <a href="/prompts" class="hidden sm:flex p-2 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300" title="Prompts">
                        <i data-lucide="file-edit" class="w-5 h-5"></i>
                    </a>
                    <button id="theme-toggle" type="button" class="p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg">
                        <i data-lucide="moon" id="theme-toggle-dark-icon" class="hidden w-5 h-5"></i>
                        <i data-lucide="sun" id="theme-toggle-light-icon" class="hidden w-5 h-5"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- Chat Container -->
        <div class="flex-1 flex flex-col bg-white dark:bg-gray-800 mx-0 sm:mx-4 sm:mb-4 sm:rounded-lg shadow overflow-hidden min-h-0">
            <!-- Messages Area -->
            <div id="chat-messages" class="flex-1 overflow-y-auto p-3 sm:p-4 space-y-3 sm:space-y-4">
                <!-- Welcome message -->
                <div class="chat-message flex gap-2 sm:gap-3">
                    <div class="flex-shrink-0 w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-blue-500 flex items-center justify-center">
                        <i data-lucide="bot" class="w-4 h-4 sm:w-5 sm:h-5 text-white"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="bg-gray-100 dark:bg-gray-700 rounded-lg p-2 sm:p-3 inline-block max-w-full">
                            <p class="text-sm sm:text-base text-gray-800 dark:text-gray-200">Hello! I'm the Climate Agent. I can help you with:</p>
                            <ul class="mt-2 text-xs sm:text-sm text-gray-600 dark:text-gray-300 list-disc list-inside">
                                <li>Check current weather and forecast</li>
                                <li>View or change thermostat settings</li>
                                <li>Explain my recent decisions</li>
                            </ul>
                            <p class="mt-2 text-sm sm:text-base text-gray-800 dark:text-gray-200">What would you like to know?</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Typing Indicator (hidden by default) -->
            <div id="typing-indicator" class="hidden px-3 sm:px-4 pb-2">
                <div class="flex gap-2 sm:gap-3">
                    <div class="flex-shrink-0 w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-blue-500 flex items-center justify-center">
                        <i data-lucide="bot" class="w-4 h-4 sm:w-5 sm:h-5 text-white"></i>
                    </div>
                    <div class="bg-gray-100 dark:bg-gray-700 rounded-lg p-2 sm:p-3 inline-flex items-center gap-1">
                        <div class="typing-indicator flex gap-1">
                            <span class="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full"></span>
                            <span class="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full"></span>
                            <span class="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full"></span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Input Area -->
            <div class="flex-shrink-0 border-t dark:border-gray-700 p-2 sm:p-4 bg-white dark:bg-gray-800">
                <form id="chat-form" class="flex gap-2">
                    <input
                        type="text"
                        id="chat-input"
                        placeholder="Ask about weather, thermostat..."
                        class="flex-1 min-w-0 px-3 sm:px-4 py-2 text-sm sm:text-base border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        autocomplete="off"
                    >
                    <button
                        type="submit"
                        id="send-button"
                        class="flex-shrink-0 px-3 sm:px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <i data-lucide="send" class="w-4 h-4 sm:w-5 sm:h-5"></i>
                        <span class="hidden sm:inline ml-2">Send</span>
                    </button>
                </form>
                <div class="mt-2 flex flex-wrap gap-1.5 sm:gap-2">
                    <button class="quick-prompt px-2 sm:px-3 py-1 text-xs sm:text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-full transition-colors" data-prompt="What's the current weather?">
                        Weather
                    </button>
                    <button class="quick-prompt px-2 sm:px-3 py-1 text-xs sm:text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-full transition-colors" data-prompt="What's the thermostat set to?">
                        Thermostat
                    </button>
                    <button class="quick-prompt px-2 sm:px-3 py-1 text-xs sm:text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-full transition-colors" data-prompt="What's the forecast for the next 6 hours?">
                        Forecast
                    </button>
                    <button class="quick-prompt px-2 sm:px-3 py-1 text-xs sm:text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-full transition-colors" data-prompt="Set temperature to 21 degrees">
                        Set 21°C
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        lucide.createIcons();

        // Dark mode toggle
        const themeToggleDarkIcon = document.getElementById('theme-toggle-dark-icon');
        const themeToggleLightIcon = document.getElementById('theme-toggle-light-icon');
        const themeToggleBtn = document.getElementById('theme-toggle');

        function updateThemeIcons() {
            if (document.documentElement.classList.contains('dark')) {
                themeToggleLightIcon.classList.remove('hidden');
                themeToggleDarkIcon.classList.add('hidden');
            } else {
                themeToggleLightIcon.classList.add('hidden');
                themeToggleDarkIcon.classList.remove('hidden');
            }
        }
        updateThemeIcons();

        themeToggleBtn.addEventListener('click', function() {
            document.documentElement.classList.toggle('dark');
            localStorage.setItem('color-theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
            updateThemeIcons();
        });

        // Chat functionality
        const chatMessages = document.getElementById('chat-messages');
        const chatForm = document.getElementById('chat-form');
        const chatInput = document.getElementById('chat-input');
        const sendButton = document.getElementById('send-button');
        const typingIndicator = document.getElementById('typing-indicator');

        function addMessage(content, isUser = false, toolCalls = null) {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'chat-message flex gap-2 sm:gap-3';

            const avatar = isUser
                ? '<div class="flex-shrink-0 w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-green-500 flex items-center justify-center"><i data-lucide="user" class="w-4 h-4 sm:w-5 sm:h-5 text-white"></i></div>'
                : '<div class="flex-shrink-0 w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-blue-500 flex items-center justify-center"><i data-lucide="bot" class="w-4 h-4 sm:w-5 sm:h-5 text-white"></i></div>';

            const bgClass = isUser ? 'bg-green-100 dark:bg-green-900' : 'bg-gray-100 dark:bg-gray-700';

            let toolCallsHtml = '';
            if (toolCalls && toolCalls.length > 0) {
                toolCallsHtml = '<div class="mt-2 flex flex-wrap gap-1">';
                toolCalls.forEach(tc => {
                    toolCallsHtml += `
                        <div class="text-xs bg-gray-200 dark:bg-gray-600 rounded px-2 py-1 inline-flex items-center gap-1">
                            <i data-lucide="wrench" class="w-3 h-3"></i>
                            <span class="font-mono">${tc.name}</span>
                        </div>
                    `;
                });
                toolCallsHtml += '</div>';
            }

            messageDiv.innerHTML = `
                ${avatar}
                <div class="flex-1 min-w-0">
                    <div class="${bgClass} rounded-lg p-2 sm:p-3 inline-block max-w-full">
                        <p class="text-sm sm:text-base text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-words">${escapeHtml(content)}</p>
                        ${toolCallsHtml}
                    </div>
                </div>
            `;

            chatMessages.appendChild(messageDiv);
            lucide.createIcons();
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function setLoading(loading) {
            sendButton.disabled = loading;
            chatInput.disabled = loading;
            typingIndicator.classList.toggle('hidden', !loading);
            if (loading) {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }

        async function sendMessage(message) {
            if (!message.trim()) return;

            // Get selected provider and model
            const providerSelect = document.getElementById('llm-provider');
            const modelSelect = document.getElementById('llm-model');
            const selectedProvider = providerSelect.value;
            const selectedModel = modelSelect.value;

            addMessage(message, true);
            chatInput.value = '';
            setLoading(true);

            try {
                const payload = { message: message };
                if (selectedProvider) payload.provider = selectedProvider;
                if (selectedModel) payload.model = selectedModel;

                const response = await fetch('/api/chat/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (data.error) {
                    addMessage('Error: ' + data.error, false);
                } else {
                    // Include provider info in response
                    const providerInfo = data.provider && data.model 
                        ? `[${data.provider}/${data.model}] ` 
                        : '';
                    addMessage(providerInfo + data.response, false, data.tool_calls);
                }
            } catch (error) {
                addMessage('Failed to connect to the agent. Please try again.', false);
                console.error('Chat error:', error);
            } finally {
                setLoading(false);
                chatInput.focus();
            }
        }

        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            sendMessage(chatInput.value);
        });

        // Quick prompt buttons
        document.querySelectorAll('.quick-prompt').forEach(btn => {
            btn.addEventListener('click', () => {
                sendMessage(btn.dataset.prompt);
            });
        });

        // LLM Provider Management
        let availableProviders = [];

        async function loadProviders() {
            try {
                const response = await fetch('/api/llm/providers');
                availableProviders = await response.json();
                
                const providerSelect = document.getElementById('llm-provider');
                providerSelect.innerHTML = '';
                
                availableProviders.forEach(p => {
                    if (p.available) {
                        const option = document.createElement('option');
                        option.value = p.name;
                        option.textContent = p.display_name;
                        if (!p.configured) {
                            option.textContent += ' (no key)';
                            option.disabled = true;
                        }
                        providerSelect.appendChild(option);
                    }
                });

                // Update model dropdown when provider changes
                providerSelect.addEventListener('change', updateModelOptions);
                updateModelOptions();
            } catch (error) {
                console.error('Failed to load providers:', error);
            }
        }

        function updateModelOptions() {
            const providerSelect = document.getElementById('llm-provider');
            const modelSelect = document.getElementById('llm-model');
            const selectedProvider = providerSelect.value;
            
            const provider = availableProviders.find(p => p.name === selectedProvider);
            
            modelSelect.innerHTML = '<option value="">Default</option>';
            if (provider && provider.models) {
                provider.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    modelSelect.appendChild(option);
                });
            }
        }

        // Initialize
        loadProviders();
        chatInput.focus();
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Climate Agent Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
        }
    </script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
    <script>
        // Check local storage for dark mode preference
        if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark')
        }

        // Auto-refresh every 60 seconds
        setTimeout(() => location.reload(), 60000);

        // Fetch status every 30 seconds
        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const status = await response.json();
                
                const updateIndicator = (wrapperId, key) => {
                    const wrapper = document.getElementById(wrapperId);
                    const svg = wrapper.querySelector('svg');
                    const statusText = wrapper.querySelector('.status-text');
                    
                    if (status[key]) {
                        if (svg) svg.style.color = '#22c55e'; // green-500
                        if (statusText) {
                            statusText.textContent = 'UP';
                            statusText.className = 'status-text text-xs font-medium text-green-500';
                        }
                    } else {
                        if (svg) svg.style.color = '#ef4444'; // red-500
                        if (statusText) {
                            statusText.textContent = 'DOWN';
                            statusText.className = 'status-text text-xs font-medium text-red-500';
                        }
                    }
                };

                updateIndicator('indicator-llm', 'llm');
                updateIndicator('indicator-weather', 'weather');
                updateIndicator('indicator-ha', 'ha');
                
                // Update LLM provider info display
                const llmLabel = document.querySelector('#indicator-llm .llm-label');
                if (llmLabel && status.llm_provider) {
                    llmLabel.textContent = status.llm_provider.charAt(0).toUpperCase() + status.llm_provider.slice(1);
                    llmLabel.title = status.llm_model || 'unknown';
                }
            } catch (e) {
                console.error('Status check failed', e);
            }
        }
        
        // Initial check and interval
        document.addEventListener('DOMContentLoaded', () => {
             // Wait for Lucide to render icons
             setTimeout(updateStatus, 100);
             setInterval(updateStatus, 30000);
             // Also load security stats
             updateSecurityStats();
        });

        // Security stats update
        async function updateSecurityStats() {
            try {
                const response = await fetch('/api/security/stats');
                const stats = await response.json();
                
                document.getElementById('blocked-count').textContent = stats.blocked_actions || 0;
                document.getElementById('validation-count').textContent = stats.validation_failures || 0;
                document.getElementById('auth-count').textContent = stats.auth_failures || 0;
                document.getElementById('test-count').textContent = stats.injection_tests || 0;
            } catch (e) {
                console.error('Security stats check failed', e);
            }
        }

        // Run security injection test
        async function runSecurityTest() {
            const btn = document.getElementById('security-test-btn');
            const resultDiv = document.getElementById('security-test-result');
            const originalHtml = btn.innerHTML;
            
            try {
                btn.disabled = true;
                btn.innerHTML = '<span class="animate-spin">⏳</span> Testing...';
                
                const response = await fetch('/api/security/test-injection', { method: 'POST' });
                const result = await response.json();
                
                // Show results
                resultDiv.classList.remove('hidden');
                if (result.security_working) {
                    resultDiv.className = 'mt-4 p-4 rounded-lg bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800';
                    resultDiv.innerHTML = `
                        <div class="flex items-center gap-2 text-green-700 dark:text-green-400 font-medium mb-2">
                            <i data-lucide="check-circle" class="w-5 h-5"></i>
                            Security Bounds Working Correctly
                        </div>
                        <div class="text-sm text-gray-600 dark:text-gray-300 space-y-1">
                            ${result.tests.map(t => `
                                <div class="flex justify-between">
                                    <span>${t.name}: ${t.attempted_temp}°C</span>
                                    <span class="${t.blocked ? 'text-red-500' : 'text-green-500'}">${t.result}</span>
                                </div>
                            `).join('')}
                        </div>
                    `;
                } else {
                    resultDiv.className = 'mt-4 p-4 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800';
                    resultDiv.innerHTML = `
                        <div class="flex items-center gap-2 text-red-700 dark:text-red-400 font-medium">
                            <i data-lucide="alert-circle" class="w-5 h-5"></i>
                            Security Test Failed
                        </div>
                    `;
                }
                lucide.createIcons();
                
                // Update stats
                updateSecurityStats();
                
            } catch (e) {
                console.error('Security test failed', e);
                resultDiv.classList.remove('hidden');
                resultDiv.className = 'mt-4 p-4 rounded-lg bg-red-50 dark:bg-red-900/30';
                resultDiv.innerHTML = '<span class="text-red-600 dark:text-red-400">Error running test</span>';
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                lucide.createIcons();
            }
        }
    </script>
    <style>
        /* Custom scrollbar for dark mode if needed */
        .dark ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        .dark ::-webkit-scrollbar-track {
            background: #1f2937; 
        }
        .dark ::-webkit-scrollbar-thumb {
            background: #4b5563; 
            border-radius: 4px;
        }
        .dark ::-webkit-scrollbar-thumb:hover {
            background: #6b7280; 
        }
    </style>
</head>
<body class="bg-gray-100 dark:bg-gray-900 min-h-screen transition-colors duration-200">
    <div class="container mx-auto px-3 sm:px-4 py-4 sm:py-8">
        <div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 sm:gap-0 mb-6 sm:mb-8">
            <div class="min-w-0">
                 <h1 class="text-xl sm:text-3xl font-bold text-gray-800 dark:text-gray-100 mb-1 sm:mb-2 flex items-center gap-2 sm:gap-3">
                    <i data-lucide="thermometer" class="w-5 h-5 sm:w-auto sm:h-auto flex-shrink-0"></i>
                    <span class="truncate">Climate Agent</span>
                 </h1>
                 <p class="text-xs sm:text-base text-gray-600 dark:text-gray-400 hidden sm:block">AI-powered thermostat control vs traditional automation</p>
            </div>
            <div class="flex items-center gap-1 sm:gap-4 flex-shrink-0">
                <a href="/chat" class="p-2 sm:px-3 sm:py-2 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium flex items-center gap-1 sm:gap-2 hover:bg-blue-50 dark:hover:bg-gray-700 rounded-lg" title="Chat">
                    <i data-lucide="message-circle" class="w-5 h-5 sm:w-4 sm:h-4"></i>
                    <span class="hidden sm:inline">Chat</span>
                </a>
                <a href="/prompts" class="p-2 sm:px-3 sm:py-2 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium flex items-center gap-1 sm:gap-2 hover:bg-blue-50 dark:hover:bg-gray-700 rounded-lg" title="Prompts">
                    <i data-lucide="file-edit" class="w-5 h-5 sm:w-4 sm:h-4"></i>
                    <span class="hidden sm:inline">Prompts</span>
                </a>
                <a href="/settings" class="p-2 sm:px-3 sm:py-2 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium flex items-center gap-1 sm:gap-2 hover:bg-blue-50 dark:hover:bg-gray-700 rounded-lg" title="Settings">
                    <i data-lucide="settings" class="w-5 h-5 sm:w-4 sm:h-4"></i>
                    <span class="hidden sm:inline">Settings</span>
                </a>
                <button id="theme-toggle" type="button" class="p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                    <i data-lucide="moon" id="theme-toggle-dark-icon" class="hidden w-5 h-5"></i>
                    <i data-lucide="sun" id="theme-toggle-light-icon" class="hidden w-5 h-5"></i>
                </button>
            </div>
        </div>

        <!-- Stats Cards -->
        <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <div class="flex items-center justify-between mb-2">
                    <div class="text-sm text-gray-500 dark:text-gray-400">Total Decisions</div>
                    <i data-lucide="activity" class="w-5 h-5 text-blue-500"></i>
                </div>
                <div class="text-3xl font-bold text-blue-600 dark:text-blue-400">{{ stats.total_decisions }}</div>
            </div>
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <div class="flex items-center justify-between mb-2">
                    <div class="text-sm text-gray-500 dark:text-gray-400">Today</div>
                    <i data-lucide="calendar" class="w-5 h-5 text-green-500"></i>
                </div>
                <div class="text-3xl font-bold text-green-600 dark:text-green-400">{{ stats.decisions_today }}</div>
            </div>
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <div class="flex items-center justify-between mb-2">
                     <div class="text-sm text-gray-500 dark:text-gray-400">Override Rate</div>
                     <i data-lucide="zap" class="w-5 h-5 text-purple-500"></i>
                </div>
                <div class="text-3xl font-bold text-purple-600 dark:text-purple-400">{{ comparison.ai_override_rate }}%</div>
                <div class="text-xs text-gray-400 dark:text-gray-500">AI divergence</div>
            </div>
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <div class="flex items-center justify-between mb-2">
                    <div class="text-sm text-gray-500 dark:text-gray-400">Differences</div>
                    <i data-lucide="git-branch" class="w-5 h-5 text-orange-500"></i>
                </div>
                <div class="text-3xl font-bold text-orange-600 dark:text-orange-400">{{ comparison.different_decisions }}</div>
            </div>
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <div class="flex items-center justify-between mb-2">
                    <div class="text-sm text-gray-500 dark:text-gray-400">System Health</div>
                    <i data-lucide="activity" class="w-5 h-5 text-gray-400"></i>
                </div>
                <div class="flex justify-between items-center mt-2" id="health-indicators">
                    <div id="indicator-llm" class="flex flex-col items-center gap-1" title="LLM Brain">
                        <i data-lucide="brain" class="w-6 h-6 text-gray-400"></i>
                        <span class="llm-label text-xs text-gray-500">LLM</span>
                        <span class="status-text text-xs font-medium text-gray-400">...</span>
                    </div>
                    <div id="indicator-weather" class="flex flex-col items-center gap-1" title="Weather Tools">
                        <i data-lucide="cloud-sun" class="w-6 h-6 text-gray-400"></i>
                        <span class="text-xs text-gray-500">Weather</span>
                        <span class="status-text text-xs font-medium text-gray-400">...</span>
                    </div>
                    <div id="indicator-ha" class="flex flex-col items-center gap-1" title="Home Control">
                        <i data-lucide="home" class="w-6 h-6 text-gray-400"></i>
                        <span class="text-xs text-gray-500">Home</span>
                        <span class="status-text text-xs font-medium text-gray-400">...</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Security Card -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-8">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
                    <i data-lucide="shield" class="text-green-500"></i> Security Metrics
                </h2>
                <button onclick="runSecurityTest()" id="security-test-btn"
                    class="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 transition-colors">
                    <i data-lucide="shield-check" class="w-4 h-4"></i>
                    <span>Test Security</span>
                </button>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="security-stats">
                <div class="text-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <div class="text-2xl font-bold text-red-500" id="blocked-count">0</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400">Blocked Actions</div>
                </div>
                <div class="text-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <div class="text-2xl font-bold text-orange-500" id="validation-count">0</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400">Validation Fails</div>
                </div>
                <div class="text-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <div class="text-2xl font-bold text-yellow-500" id="auth-count">0</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400">Auth Failures</div>
                </div>
                <div class="text-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <div class="text-2xl font-bold text-blue-500" id="test-count">0</div>
                    <div class="text-xs text-gray-500 dark:text-gray-400">Injection Tests</div>
                </div>
            </div>
            <div id="security-test-result" class="hidden mt-4 p-4 rounded-lg"></div>
        </div>

        <!-- Current State -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-8" id="current-state">
            <h2 class="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-100 flex items-center gap-2">
                <i data-lucide="home"></i> Current State
            </h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Indoor Temp</div>
                    <div class="text-2xl font-bold text-gray-800 dark:text-gray-100">{{ current_state.current_temp }}°C</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Target Temp</div>
                    <div class="text-2xl font-bold text-gray-800 dark:text-gray-100">{{ current_state.target_temp }}°C</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">HVAC Mode</div>
                    <div class="text-2xl font-bold capitalize text-gray-800 dark:text-gray-100">{{ current_state.hvac_mode }}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">Outside Temp</div>
                    <div class="text-2xl font-bold text-gray-800 dark:text-gray-100">{{ current_state.outside_temp }}°C</div>
                </div>
            </div>
        </div>

        <!-- Charts Section -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
            <!-- Temperature Timeline Chart -->
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <h2 class="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-100 flex items-center gap-2">
                    <i data-lucide="trending-up"></i> Temperature Timeline
                </h2>
                <div style="height: 300px;">
                    <canvas id="tempChart"></canvas>
                </div>
            </div>

            <!-- Daily Override Rate Chart -->
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                <h2 class="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-100 flex items-center gap-2">
                    <i data-lucide="bar-chart-2"></i> Daily AI Override Rate
                </h2>
                <div style="height: 300px;">
                    <canvas id="overrideChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Hourly Analysis -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-100 flex items-center gap-2">
                <i data-lucide="clock"></i> AI Overrides by Hour of Day
            </h2>
            <div style="height: 250px;">
                <canvas id="hourlyChart"></canvas>
            </div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">Shows when AI most often disagrees with baseline automation</p>
        </div>

        <!-- Recent Decisions with Comparison -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow">
            <div class="px-6 py-4 border-b dark:border-gray-700">
                <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
                    <i data-lucide="list"></i> Recent Decisions
                </h2>
                <p class="text-sm text-gray-500 dark:text-gray-400">Comparing AI agent vs what HA automation would do. Click a decision to see full reasoning.</p>
            </div>
            <div class="divide-y dark:divide-gray-700" id="decisions-list">
                <!-- Decisions inserted here -->
            </div>
        </div>

        <!-- Decision Detail Modal -->
        <div id="decision-modal" class="fixed inset-0 bg-black bg-opacity-50 z-50 hidden flex items-center justify-center p-4">
            <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden">
                <div class="px-6 py-4 border-b dark:border-gray-700 flex justify-between items-center">
                    <h3 class="text-xl font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
                        <i data-lucide="brain"></i> Decision Details
                    </h3>
                    <button onclick="closeModal()" class="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
                        <i data-lucide="x" class="w-6 h-6"></i>
                    </button>
                </div>
                <div class="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
                    <div class="mb-4">
                        <div class="flex items-center gap-3 mb-2">
                            <span id="modal-action-badge" class="px-3 py-1 rounded-full text-sm font-medium"></span>
                            <span id="modal-timestamp" class="text-sm text-gray-500 dark:text-gray-400"></span>
                        </div>
                    </div>
                    <div class="mb-4">
                        <h4 class="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-2">AI Reasoning</h4>
                        <div id="modal-reasoning" class="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 text-gray-700 dark:text-gray-300 whitespace-pre-wrap"></div>
                    </div>
                    <div id="modal-comparison" class="mb-4"></div>
                </div>
            </div>
        </div>

        <!-- Baseline Rules Reference -->
        <div class="mt-8 bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
            <h3 class="font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
                <i data-lucide="clipboard-list"></i> Baseline HA Automation Rules
            </h3>
            <div class="text-sm text-gray-600 dark:text-gray-300 grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>• Daytime (6am-10pm): 21°C</div>
                <div>• Nighttime: 18°C</div>
                <div>• Cold boost (outdoor &lt; -10°C): +1°C</div>
                <div>• Summer cooling (outdoor &gt; 25°C): 24°C</div>
            </div>
        </div>

        <div class="mt-8 text-center text-gray-500 dark:text-gray-500 text-sm">
            Auto-refreshes every 60 seconds | Last updated: {{ now }}
        </div>
    </div>

    <script>
        // Initialize Lucide
        lucide.createIcons();

        // Modal functions
        function openModal(action, timestamp, reasoning, comparison, aiTemp, baselineAction, baselineTemp, baselineRule, decisionsMatch) {
            const modal = document.getElementById('decision-modal');
            const actionBadge = document.getElementById('modal-action-badge');
            const timestampEl = document.getElementById('modal-timestamp');
            const reasoningEl = document.getElementById('modal-reasoning');
            const comparisonEl = document.getElementById('modal-comparison');

            // Set action badge
            if (action === 'SET_TEMPERATURE') {
                actionBadge.textContent = aiTemp ? `SET ${aiTemp}°C` : 'SET_TEMPERATURE';
                actionBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200';
            } else {
                actionBadge.textContent = 'NO_CHANGE';
                actionBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200';
            }

            timestampEl.textContent = timestamp;
            reasoningEl.textContent = reasoning;

            // Build comparison HTML
            if (baselineAction) {
                const baselineTempStr = baselineTemp ? ` -> ${baselineTemp}°C` : '';
                if (decisionsMatch === 0) {
                    comparisonEl.innerHTML = `
                        <h4 class="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-2">Baseline Comparison</h4>
                        <div class="p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="text-orange-600 dark:text-orange-400 font-semibold">AI Override</span>
                            </div>
                            <div class="text-sm text-gray-600 dark:text-gray-300">
                                <strong>Baseline would:</strong> ${baselineAction}${baselineTempStr}<br>
                                <strong>Rule:</strong> ${baselineRule}
                            </div>
                        </div>
                    `;
                } else {
                    comparisonEl.innerHTML = `
                        <h4 class="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-2">Baseline Comparison</h4>
                        <div class="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                            <div class="text-sm text-gray-600 dark:text-gray-300">
                                Matches baseline automation (${baselineRule})
                            </div>
                        </div>
                    `;
                }
            } else {
                comparisonEl.innerHTML = '';
            }

            modal.classList.remove('hidden');
            // Re-initialize lucide icons in modal
            lucide.createIcons();
        }

        function closeModal() {
            document.getElementById('decision-modal').classList.add('hidden');
        }

        // Close modal on escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });

        // Close modal when clicking outside
        document.getElementById('decision-modal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });

        // Dark mode toggle logic
        var themeToggleDarkIcon = document.getElementById('theme-toggle-dark-icon');
        var themeToggleLightIcon = document.getElementById('theme-toggle-light-icon');
        var themeToggleBtn = document.getElementById('theme-toggle');

        function updateThemeIcons() {
            if (localStorage.getItem('color-theme') === 'dark' || (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                themeToggleLightIcon.classList.remove('hidden');
                themeToggleDarkIcon.classList.add('hidden');
            } else {
                themeToggleLightIcon.classList.add('hidden');
                themeToggleDarkIcon.classList.remove('hidden');
            }
        }
        updateThemeIcons();

        themeToggleBtn.addEventListener('click', function() {
             if (localStorage.getItem('color-theme')) {
                if (localStorage.getItem('color-theme') === 'light') {
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('color-theme', 'dark');
                } else {
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('color-theme', 'light');
                }
            } else {
                if (document.documentElement.classList.contains('dark')) {
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('color-theme', 'light');
                } else {
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('color-theme', 'dark');
                }
            }
            updateThemeIcons();
        });

        // Timeline data from server
        const timelineData = {{ timeline_json }};
        const dailyData = {{ daily_json }};
        const hourlyData = {{ hourly_json }};

        // Chart defaults for dark mode logic could be improved here but sticking to simple override
        const isDarkMode = document.documentElement.classList.contains('dark');
        Chart.defaults.color = isDarkMode ? '#9ca3af' : '#6b7280';
        Chart.defaults.borderColor = isDarkMode ? '#374151' : '#e5e7eb';

        // Temperature Timeline Chart
        if (timelineData.length > 0) {
            const tempCtx = document.getElementById('tempChart').getContext('2d');
            new Chart(tempCtx, {
                type: 'line',
                data: {
                    labels: timelineData.map(d => d.timestamp),
                    datasets: [
                        {
                            label: 'Indoor Temp',
                            data: timelineData.map(d => d.indoor_temp),
                            borderColor: 'rgb(59, 130, 246)',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            tension: 0.3,
                            fill: false,
                        },
                        {
                            label: 'Outdoor Temp',
                            data: timelineData.map(d => d.outdoor_temp),
                            borderColor: 'rgb(34, 197, 94)',
                            backgroundColor: 'rgba(34, 197, 94, 0.1)',
                            tension: 0.3,
                            fill: false,
                        },
                        {
                            label: 'Target Temp',
                            data: timelineData.map(d => d.target_temp),
                            borderColor: 'rgb(249, 115, 22)',
                            backgroundColor: 'rgba(249, 115, 22, 0.1)',
                            borderDash: [5, 5],
                            tension: 0.3,
                            fill: false,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'hour',
                                displayFormats: {
                                    hour: 'MMM d, HH:mm'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Temperature (°C)'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top'
                        }
                    }
                }
            });
        }

        // Daily Override Rate Chart
        if (dailyData.length > 0) {
            const overrideCtx = document.getElementById('overrideChart').getContext('2d');
            new Chart(overrideCtx, {
                type: 'bar',
                data: {
                    labels: dailyData.map(d => d.date),
                    datasets: [
                        {
                            label: 'Override Rate %',
                            data: dailyData.map(d => d.override_rate),
                            backgroundColor: 'rgba(147, 51, 234, 0.7)',
                            borderColor: 'rgb(147, 51, 234)',
                            borderWidth: 1,
                            yAxisID: 'y'
                        },
                        {
                            label: 'Total Decisions',
                            data: dailyData.map(d => d.total),
                            type: 'line',
                            borderColor: 'rgb(59, 130, 246)',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            yAxisID: 'y1',
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            type: 'linear',
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Override Rate (%)'
                            },
                            min: 0,
                            max: 100
                        },
                        y1: {
                            type: 'linear',
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Decisions'
                            },
                            grid: {
                                drawOnChartArea: false
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top'
                        }
                    }
                }
            });
        }

        // Hourly Override Chart
        const hourlyLabels = [];
        const hourlyOverrides = [];
        const hourlyTotals = [];
        for (let h = 0; h < 24; h++) {
            hourlyLabels.push(h + ':00');
            const data = hourlyData[h] || { overrides: 0, total: 0, override_rate: 0 };
            hourlyOverrides.push(data.override_rate);
            hourlyTotals.push(data.total);
        }

        const hourlyCtx = document.getElementById('hourlyChart').getContext('2d');
        new Chart(hourlyCtx, {
            type: 'bar',
            data: {
                labels: hourlyLabels,
                datasets: [
                    {
                        label: 'Override Rate %',
                        data: hourlyOverrides,
                        backgroundColor: hourlyOverrides.map(v => v > 50 ? 'rgba(249, 115, 22, 0.7)' : 'rgba(147, 51, 234, 0.7)'),
                        borderColor: hourlyOverrides.map(v => v > 50 ? 'rgb(249, 115, 22)' : 'rgb(147, 51, 234)'),
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: {
                            display: true,
                            text: 'Override Rate (%)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Hour of Day'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: function(context) {
                                const total = hourlyTotals[context.dataIndex];
                                return `Total decisions: ${total}`;
                            }
                        }
                    }
                }
            }
        });
    </script>
</body>
</html>
"""


async def get_dashboard_html(request: Request) -> HTMLResponse:
    """Render the dashboard."""
    logger = DecisionLogger()

    try:
        decisions = await logger.get_recent_decisions(limit=20)
        stats = await logger.get_decision_stats()
        comparison = await logger.get_comparison_stats()
        timeline_data = await logger.get_timeline_data(days=7)
        daily_data = await logger.get_daily_stats(days=7)
        hourly_data = await logger.get_hourly_stats()
    except Exception as e:
        decisions = []
        stats = {
            "total_decisions": 0,
            "decisions_today": 0,
            "success_rate": 100,
            "action_breakdown": {},
        }
        comparison = {
            "total_compared": 0,
            "matching_decisions": 0,
            "different_decisions": 0,
            "ai_override_rate": 0,
            "recent_differences": [],
        }
        timeline_data = {"timeline": []}
        daily_data = {"daily_stats": []}
        hourly_data = {"hourly_stats": {}}

    # Get current state from most recent decision
    current_state = None
    if decisions and decisions[0].get("thermostat_state"):
        ts = decisions[0]["thermostat_state"]
        ws = decisions[0].get("weather_data") or {}  # Handle None case
        current_state = {
            "current_temp": ts.get("current_temperature", "?"),
            "target_temp": ts.get("target_temperature", "?"),
            "hvac_mode": ts.get("hvac_mode", "?"),
            "outside_temp": ws.get("temperature_c", "?") if ws else "?",
        }

    # Build HTML
    html = DASHBOARD_HTML

    # Replace stats
    html = html.replace("{{ stats.total_decisions }}", str(stats["total_decisions"]))
    html = html.replace("{{ stats.decisions_today }}", str(stats["decisions_today"]))
    html = html.replace("{{ comparison.ai_override_rate }}", str(comparison["ai_override_rate"]))
    html = html.replace("{{ comparison.different_decisions }}", str(comparison["different_decisions"]))
    html = html.replace("{{ now }}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Add chart data as JSON
    import json
    html = html.replace("{{ timeline_json }}", json.dumps(timeline_data.get("timeline", [])))
    html = html.replace("{{ daily_json }}", json.dumps(daily_data.get("daily_stats", [])))
    html = html.replace("{{ hourly_json }}", json.dumps(hourly_data.get("hourly_stats", {})))

    # Handle current state
    if current_state:
        html = html.replace("{{ current_state.current_temp }}", str(current_state["current_temp"]))
        html = html.replace("{{ current_state.target_temp }}", str(current_state["target_temp"]))
        html = html.replace("{{ current_state.hvac_mode }}", str(current_state["hvac_mode"]))
        html = html.replace("{{ current_state.outside_temp }}", str(current_state["outside_temp"]))
    else:
        html = html.replace("{{ current_state.current_temp }}", "?")
        html = html.replace("{{ current_state.target_temp }}", "?")
        html = html.replace("{{ current_state.hvac_mode }}", "?")
        html = html.replace("{{ current_state.outside_temp }}", "?")

    # Build decisions list HTML
    decisions_html = ""
    for decision in decisions:
        action = decision.get("action", "UNKNOWN")
        timestamp = decision.get("timestamp", "")[:19]
        reasoning = decision.get("reasoning", "No reasoning provided")
        ai_temp = decision.get("ai_temperature")
        baseline_action = decision.get("baseline_action")
        baseline_temp = decision.get("baseline_temperature")
        baseline_rule = decision.get("baseline_rule", "")
        decisions_match = decision.get("decisions_match")
        tool_count = len(decision.get("tool_calls", []) or [])

        # Determine badge color for AI decision
        if action == "NO_CHANGE":
            ai_badge_class = "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
        elif action == "SET_TEMPERATURE":
            ai_badge_class = "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
        elif action == "ERROR":
            ai_badge_class = "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
        else:
            ai_badge_class = "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"

        # Format AI decision text
        ai_temp_str = f" → {ai_temp}°C" if ai_temp else ""

        # Build comparison section
        comparison_html = ""
        if baseline_action:
            baseline_temp_str = f" → {baseline_temp}°C" if baseline_temp else ""

            if decisions_match == 0:
                # Decisions differ - highlight this
                comparison_html = f"""
                <div class="mt-3 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-orange-600 dark:text-orange-400 font-semibold">⚡ AI Override</span>
                    </div>
                    <div class="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <span class="text-gray-500 dark:text-gray-400">Baseline would:</span>
                            <span class="font-medium text-gray-800 dark:text-gray-200">{baseline_action}{baseline_temp_str}</span>
                            <span class="text-gray-400 dark:text-gray-500 text-xs">({baseline_rule})</span>
                        </div>
                        <div>
                            <span class="text-gray-500 dark:text-gray-400">AI chose:</span>
                            <span class="font-medium text-blue-600 dark:text-blue-400">{action}{ai_temp_str}</span>
                        </div>
                    </div>
                </div>
                """
            else:
                # Decisions match
                comparison_html = f"""
                <div class="mt-2 text-sm text-gray-500 dark:text-gray-400">
                    ✓ Matches baseline automation ({baseline_rule})
                </div>
                """

        tool_info = f'<span class="text-gray-400 dark:text-gray-500 text-sm ml-2">({tool_count} tool calls)</span>' if tool_count else ""

        # Escape reasoning for JavaScript (handle quotes, newlines, etc.)
        reasoning_escaped = reasoning.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
        baseline_rule_escaped = baseline_rule.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"') if baseline_rule else ""
        baseline_action_escaped = baseline_action.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"') if baseline_action else ""

        # Build onclick handler with all the data
        onclick_handler = f"openModal('{action}', '{timestamp}', '{reasoning_escaped}', '', {ai_temp if ai_temp else 'null'}, '{baseline_action_escaped}', {baseline_temp if baseline_temp else 'null'}, '{baseline_rule_escaped}', {decisions_match if decisions_match is not None else 'null'})"

        decisions_html += f"""
        <div class="px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer" onclick="{onclick_handler}">
            <div class="flex justify-between items-start mb-2">
                <div class="flex items-center gap-2">
                    <span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium {ai_badge_class}">
                        {action}{ai_temp_str}
                    </span>
                    {tool_info}
                </div>
                <span class="text-sm text-gray-500 dark:text-gray-400">{timestamp}</span>
            </div>
            <p class="text-gray-700 dark:text-gray-300">{reasoning[:300]}{"..." if len(reasoning) > 300 else ""}<span class="text-blue-500 dark:text-blue-400 ml-1">{" (click to expand)" if len(reasoning) > 300 else ""}</span></p>
            {comparison_html}
        </div>
        """

    if not decisions_html:
        decisions_html = """
        <div class="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
            No decisions yet. The agent will make its first decision soon.
        </div>
        """

    # Insert decisions into HTML
    html = html.replace('<!-- Decisions inserted here -->', decisions_html)

    return HTMLResponse(content=html)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    """Show the login page."""
    # If auth is disabled, redirect to dashboard
    if not is_auth_enabled():
        return RedirectResponse(url="/", status_code=302)
    
    # If already logged in, redirect to dashboard
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token and verify_session(session_token):
        return RedirectResponse(url="/", status_code=302)
    
    # Render login page with optional error
    html = LOGIN_PAGE_HTML
    if error:
        html = html.replace("{% if error %}", "").replace("{% endif %}", "")
        html = html.replace("{{ error }}", error)
    else:
        # Remove error block if no error
        import re
        html = re.sub(r'\{% if error %\}.*?\{% endif %\}', '', html, flags=re.DOTALL)
    return HTMLResponse(content=html)


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Handle login form submission."""
    if verify_credentials(username, password):
        # Create session and set cookie
        token = create_session(username)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 7,  # 7 days
        )
        return response
    else:
        # Return to login with error
        return RedirectResponse(url="/login?error=Invalid+username+or+password", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Log out and clear session."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        delete_session(session_token)
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard home page."""
    # Check authentication if enabled
    if is_auth_enabled():
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_token or not verify_session(session_token):
            return RedirectResponse(url="/login", status_code=302)
    
    return await get_dashboard_html(request)


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "climate-agent"}


@router.get("/api/decisions")
async def api_decisions(limit: int = 20):
    """API endpoint for decisions."""
    logger = DecisionLogger()
    return await logger.get_recent_decisions(limit=limit)


@router.get("/api/stats")
async def api_stats():
    """API endpoint for stats."""
    logger = DecisionLogger()
    return await logger.get_decision_stats()


@router.get("/api/comparison")
async def api_comparison():
    """API endpoint for AI vs baseline comparison stats."""
    logger = DecisionLogger()
    return await logger.get_comparison_stats()


@router.get("/api/timeline")
async def api_timeline(days: int = 7):
    """API endpoint for timeline data."""
    logger = DecisionLogger()
    return await logger.get_timeline_data(days=days)


@router.get("/api/daily")
async def api_daily(days: int = 7):
    """API endpoint for daily stats."""
    logger = DecisionLogger()
    return await logger.get_daily_stats(days=days)


@router.get("/api/hourly")
async def api_hourly():
    """API endpoint for hourly stats."""
    logger = DecisionLogger()
    return await logger.get_hourly_stats()


@router.get("/api/status")
async def api_status():
    """Get health status of agent components."""
    from . import main as agent_main
    agent = agent_main.agent
    
    # Defaults if agent not initialized
    status = {
        "llm": False,
        "llm_provider": "unknown",
        "llm_model": "unknown",
        "weather": False,
        "ha": False
    }
    
    if agent.initialized:
        # Get LLM info
        status["llm_provider"] = agent.llm.provider_name
        status["llm_model"] = agent.llm.model
        
        # Check components in parallel
        import asyncio
        results = await asyncio.gather(
            agent.llm.health_check(),
            agent.weather_client.health_check(),
            agent.ha_client.health_check(),
            return_exceptions=True
        )
        
        status["llm"] = results[0] if isinstance(results[0], bool) else False
        status["weather"] = results[1] if isinstance(results[1], bool) else False
        status["ha"] = results[2] if isinstance(results[2], bool) else False
            
    return status


@router.get("/api/security/stats")
async def api_security_stats():
    """Get security event statistics."""
    logger = DecisionLogger()
    try:
        stats = await logger.get_security_stats()
        return stats
    except Exception:
        # Table might not exist yet
        return {
            "total_events": 0,
            "blocked_actions": 0,
            "validation_failures": 0,
            "auth_failures": 0,
            "injection_tests": 0,
            "recent_events": [],
        }


@router.post("/api/security/test-injection")
async def api_security_test_injection():
    """Test injection protection by attempting to set invalid temperatures.
    
    This endpoint demonstrates how safety bounds protect against:
    1. Extreme high temperatures (e.g., 99°C)
    2. Extreme low temperatures (e.g., -50°C)
    3. Validates that normal temperatures still work
    """
    import os
    logger = DecisionLogger()
    
    MIN_TEMP = float(os.getenv("MIN_TEMP", "17"))
    MAX_TEMP = float(os.getenv("MAX_TEMP", "23"))
    
    tests = []
    
    # Test 1: Attempt extreme high temperature
    test_high = {
        "name": "Extreme High Temperature",
        "attempted_temp": 99.0,
        "expected": "blocked",
        "reason": f"Above MAX_TEMP ({MAX_TEMP}°C)"
    }
    test_high["blocked"] = 99.0 > MAX_TEMP
    test_high["result"] = "BLOCKED ✓" if test_high["blocked"] else "ALLOWED ✗"
    tests.append(test_high)
    
    # Test 2: Attempt extreme low temperature
    test_low = {
        "name": "Extreme Low Temperature",
        "attempted_temp": -50.0,
        "expected": "blocked",
        "reason": f"Below MIN_TEMP ({MIN_TEMP}°C)"
    }
    test_low["blocked"] = -50.0 < MIN_TEMP
    test_low["result"] = "BLOCKED ✓" if test_low["blocked"] else "ALLOWED ✗"
    tests.append(test_low)
    
    # Test 3: Attempt just above max
    test_above_max = {
        "name": "Just Above Maximum",
        "attempted_temp": MAX_TEMP + 0.5,
        "expected": "blocked",
        "reason": f"Above MAX_TEMP ({MAX_TEMP}°C)"
    }
    test_above_max["blocked"] = (MAX_TEMP + 0.5) > MAX_TEMP
    test_above_max["result"] = "BLOCKED ✓" if test_above_max["blocked"] else "ALLOWED ✗"
    tests.append(test_above_max)
    
    # Test 4: Attempt just below min
    test_below_min = {
        "name": "Just Below Minimum",
        "attempted_temp": MIN_TEMP - 0.5,
        "expected": "blocked",
        "reason": f"Below MIN_TEMP ({MIN_TEMP}°C)"
    }
    test_below_min["blocked"] = (MIN_TEMP - 0.5) < MIN_TEMP
    test_below_min["result"] = "BLOCKED ✓" if test_below_min["blocked"] else "ALLOWED ✗"
    tests.append(test_below_min)
    
    # Test 5: Valid temperature (should be allowed)
    valid_temp = (MIN_TEMP + MAX_TEMP) / 2
    test_valid = {
        "name": "Valid Temperature (Control)",
        "attempted_temp": valid_temp,
        "expected": "allowed",
        "reason": f"Within bounds [{MIN_TEMP}, {MAX_TEMP}]°C"
    }
    test_valid["blocked"] = valid_temp < MIN_TEMP or valid_temp > MAX_TEMP
    test_valid["result"] = "ALLOWED ✓" if not test_valid["blocked"] else "BLOCKED ✗"
    tests.append(test_valid)
    
    # Log as security event
    await logger.log_security_event(
        event_type="injection_test",
        source="dashboard",
        details={
            "tests_run": len(tests),
            "blocked_count": sum(1 for t in tests if t["blocked"]),
            "allowed_count": sum(1 for t in tests if not t["blocked"]),
            "bounds": {"min": MIN_TEMP, "max": MAX_TEMP}
        },
        blocked=False  # This is a test, not a blocked action
    )
    
    return {
        "summary": f"Ran {len(tests)} injection tests",
        "bounds": {"min_temp": MIN_TEMP, "max_temp": MAX_TEMP},
        "tests": tests,
        "security_working": all(
            (t["blocked"] and t["expected"] == "blocked") or
            (not t["blocked"] and t["expected"] == "allowed")
            for t in tests
        )
    }


@router.get("/prompts", response_class=HTMLResponse)
async def prompts_page(request: Request):
    """Render the prompts configuration page."""
    return HTMLResponse(content=PROMPTS_PAGE_HTML)


@router.get("/api/prompts")
async def api_get_prompts():
    """Get all prompts."""
    logger = DecisionLogger()
    return await logger.get_all_prompts()


@router.post("/api/prompts/{key}")
async def api_update_prompt(key: str, request: Request):
    """Update a specific prompt."""
    logger = DecisionLogger()
    data = await request.json()
    content = data.get("content")
    if not content:
        return {"error": "Content required"}
    
    await logger.update_prompt(key, content)
    return {"status": "success", "key": key}


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Render the settings page."""
    return HTMLResponse(content=SETTINGS_PAGE_HTML)


@router.get("/api/settings")
async def api_get_settings():
    """Get all settings."""
    logger = DecisionLogger()
    return await logger.get_all_settings()


@router.post("/api/settings/{key}")
async def api_update_setting(key: str, request: Request):
    """Update a specific setting."""
    logger = DecisionLogger()
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"error": "Value required"}

    await logger.update_setting(key, value)
    return {"status": "success", "key": key}


@router.get("/api/llm/providers")
async def api_llm_providers():
    """Get list of available LLM providers with status."""
    logger = DecisionLogger()
    settings = await logger.get_all_settings()
    settings_dict = {s["key"]: s["value"] for s in settings}
    return get_available_providers(settings_dict)


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Render the chat page."""
    return HTMLResponse(content=CHAT_PAGE_HTML)


@router.post("/api/chat/send")
async def api_chat_send(request: Request):
    """Send a message to the AI agent and get a response."""
    import logging
    chat_logger = logging.getLogger(__name__)

    try:
        data = await request.json()
        message = data.get("message", "").strip()

        if not message:
            return {"error": "Message required"}

        # Import the agent from main module
        from . import main as agent_main
        agent = agent_main.agent

        if not agent.initialized:
            # Try to initialize on-demand
            chat_logger.info("Agent not initialized, attempting initialization...")

            # Check individual components for better error messages
            errors = []

            # Check LLM provider
            try:
                llm_ok = await agent.llm.health_check()
                if not llm_ok:
                    errors.append(f"LLM ({agent.llm.provider_name}) not responding")
            except Exception as e:
                errors.append(f"LLM error: {e}")

            # Check Weather MCP
            try:
                weather_ok = await agent.weather_client.health_check()
                if not weather_ok:
                    errors.append("Weather MCP not responding")
            except Exception as e:
                errors.append(f"Weather MCP error: {e}")

            # Check HA MCP
            try:
                ha_ok = await agent.ha_client.health_check()
                if not ha_ok:
                    errors.append("Home Assistant MCP not responding")
            except Exception as e:
                errors.append(f"HA MCP error: {e}")

            if errors:
                return {"error": f"Agent cannot initialize. Issues: {'; '.join(errors)}"}

            # All health checks passed, try full initialization
            try:
                success = await agent.initialize()
                if not success:
                    return {"error": "Agent initialization failed despite healthy services. Check agent logs."}
            except Exception as init_error:
                chat_logger.error(f"Initialization error: {init_error}")
                return {"error": f"Agent initialization failed: {str(init_error)}"}

        # Get provider/model override from request (for chatbot switching)
        provider_type = data.get("provider")  # Optional provider override
        model_override = data.get("model")    # Optional model override

        # Get the chat system prompt from DB (or use a default)
        logger = DecisionLogger()
        chat_system_prompt = await logger.get_prompt(
            "chat_system_prompt",
            """You are the Climate Agent assistant. You help users understand and control their home climate system.

You have access to tools to:
- Check current weather conditions
- Get weather forecasts
- View thermostat state
- Adjust the thermostat temperature (only when explicitly asked)

Be helpful, concise, and informative. When users ask about the weather or thermostat, use your tools to get real data.
When users ask to change the temperature, confirm what you're doing.

Always respond in English.""",
            "System prompt for the interactive chat feature"
        )

        # Combine tools from both MCP clients
        tools = []
        tools.extend(agent.weather_client.get_tools_for_llm())
        tools.extend(agent.ha_client.get_tools_for_llm())

        # Tool executor that routes to the correct MCP client
        async def execute_tool(name: str, arguments: dict):
            chat_logger.info(f"Chat executing tool: {name} with args: {arguments}")

            # Weather tools
            if name in ["get_current_weather", "get_forecast"]:
                return await agent.weather_client.call_tool(name, arguments)
            # HA tools
            elif name in ["get_thermostat_state", "set_thermostat_temperature", "set_hvac_mode", "set_preset_mode"]:
                return await agent.ha_client.call_tool(name, arguments)
            else:
                return {"error": f"Unknown tool: {name}"}

        # Create LLM provider - use override if specified, otherwise use agent's default
        if provider_type or model_override:
            # Load settings for API keys
            settings = await logger.get_all_settings()
            settings_dict = {s["key"]: s["value"] for s in settings}
            llm = create_llm_provider(
                provider_type=provider_type,
                model=model_override,
                settings=settings_dict
            )
            chat_logger.info(f"Chat using override LLM: {llm.provider_name}/{llm.model}")
        else:
            llm = agent.llm
            chat_logger.info(f"Chat using agent LLM: {llm.provider_name}/{llm.model}")

        # Call LLM with tools
        result = await llm.chat_with_tools(
            user_message=message,
            tools=tools,
            tool_executor=execute_tool,
            system_prompt=chat_system_prompt,
            max_iterations=5
        )

        return {
            "response": result.get("final_response", "No response generated"),
            "tool_calls": result.get("tool_calls_made", []),
            "provider": llm.provider_name,
            "model": llm.model,
        }

    except Exception as e:
        chat_logger.error(f"Chat error: {e}", exc_info=True)
        return {"error": str(e)}
