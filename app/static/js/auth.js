/**
 * auth.js — Login form handling
 */
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    const errorEl = document.getElementById('login-error');
    const btn = document.getElementById('login-btn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorEl.style.display = 'none';
        btn.disabled = true;
        btn.textContent = 'Вход...';

        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await res.json();

            if (res.ok) {
                API.setToken(data.access_token);
                API.setUser({ username: data.username, role: data.role });
                window.location.href = '/dashboard';
            } else {
                errorEl.textContent = data.detail || 'Ошибка авторизации';
                errorEl.style.display = 'block';
                errorEl.classList.add('animate-shake');
                setTimeout(() => errorEl.classList.remove('animate-shake'), 400);
            }
        } catch (err) {
            errorEl.textContent = 'Ошибка соединения с сервером';
            errorEl.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Войти';
        }
    });
});
