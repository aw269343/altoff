/**
 * api.js — Fetch wrapper with JWT Bearer token
 */
const API = {
    getToken() {
        return localStorage.getItem('alto_token');
    },

    setToken(token) {
        localStorage.setItem('alto_token', token);
    },

    setUser(user) {
        localStorage.setItem('alto_user', JSON.stringify(user));
    },

    getUser() {
        try {
            return JSON.parse(localStorage.getItem('alto_user'));
        } catch {
            return null;
        }
    },

    logout() {
        localStorage.removeItem('alto_token');
        localStorage.removeItem('alto_user');
        window.location.href = '/';
    },

    async request(url, options = {}) {
        const token = this.getToken();
        const headers = options.headers || {};

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        if (options.body && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
            if (typeof options.body !== 'string') {
                options.body = JSON.stringify(options.body);
            }
        }

        options.headers = headers;

        const res = await fetch(url, options);

        if (res.status === 401) {
            this.logout();
            return null;
        }

        return res;
    },

    async get(url) {
        const res = await this.request(url);
        if (!res) return null;
        return res.json();
    },

    async post(url, body) {
        const res = await this.request(url, { method: 'POST', body });
        if (!res) return null;
        return res.json();
    },

    async postFile(url, file) {
        const fd = new FormData();
        fd.append('file', file);
        const res = await this.request(url, { method: 'POST', body: fd });
        if (!res) return null;
        return res.json();
    },

    async del(url) {
        const res = await this.request(url, { method: 'DELETE' });
        if (!res) return null;
        return res.json();
    },

    async download(url, fallbackFilename) {
        try {
            const token = this.getToken();
            const res = await fetch(url, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            
            if (res.status === 401) {
                this.logout();
                return;
            }
            
            if (!res.ok) {
                try {
                    const err = await res.json();
                    console.error("Download error response:", err);
                    if (window.showToast) window.showToast(err.detail || 'Ошибка скачивания', 'error');
                } catch (e) {
                    console.error("Download fallback error:", e);
                    if (window.showToast) window.showToast('Ошибка скачивания', 'error');
                }
                return;
            }

            const disposition = res.headers.get('Content-Disposition');
            let filename = fallbackFilename || 'report.xlsx';
            
            if (disposition && disposition.includes("filename*=UTF-8''")) {
                filename = decodeURIComponent(disposition.split("filename*=UTF-8''")[1]);
            } else if (disposition && disposition.includes('filename=')) {
                filename = disposition.split('filename=')[1].replace(/['"]/g, '');
            }
            
            const blob = await res.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            
            a.style.display = 'none';
            a.href = downloadUrl;
            a.download = decodeURIComponent(filename); // Убедимся, что кириллица декодирована
            
            document.body.appendChild(a);
            a.click();
            
            // Задержка для очистки памяти (особенно важно для Safari на Mac)
            setTimeout(() => {
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);
            }, 1000);
            
        } catch (error) {
            console.error("Network or parsing error during download:", error);
            if (window.showToast) window.showToast('Ошибка сети при скачивании', 'error');
        }
    },
};
