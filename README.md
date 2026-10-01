# SYNERA – řízení provozu MPDMB

Verze **0.8.1** (zdroj: `apps/core/version.py`; historie v `CHANGELOG.md`).
Webová aplikace SYNERA pro řízení zaměstnanců a provozu parkovacích
domů v Mladé Boleslavi. Běží v prohlížeči (Django + SQLite).

## Požadavky

- Windows 10+
- Python 3.12+ (ověřeno s 3.14)
- SQLite (součást Pythonu/Django; nic dalšího se neinstaluje)

## Instalace (vývoj)

```powershell
cd F:\Python\MPDMB
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Upravte `.env`: `SECRET_KEY` a `ALLOWED_HOSTS` (localhost, 127.0.0.1
a skutečná IPv4 počítače). Databáze je soubor `db.sqlite3`.

Migrace, vývojový administrátor a spuštění serveru:

```powershell
.\start-dev.bat
```

Přihlášení do aplikace (lokální vývoj): **Jméno `Holub`**, **heslo `22552255`**.
Vstup na `http://127.0.0.1:8000/` vyžaduje přihlášení (`/prihlaseni/`).

## Spuštění (vývoj)

```powershell
.\start-dev.bat
```

Ruční alternativa:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py ensure_dev_admin
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

- Aplikace: http://127.0.0.1:8000/
- Nápověda: http://127.0.0.1:8000/napoveda/
- Administrace (rozcestník): http://127.0.0.1:8000/administrace/
- Django admin (detaily): http://127.0.0.1:8000/admin/
- Z jiné stanice v síti/VPN: http://<IPv4-počítače>:8000/
- Zdravotní kontrola: http://127.0.0.1:8000/health/

IPv4 zjistěte příkazem `ipconfig`. Port 8000 povolte ve firewallu
jen pro důvěryhodnou síť/VPN.

Rozcestník `/administrace/` a dlaždice Administrace jsou pro
superuživatele nebo staff ve skupině **administrátor**. Provozní data
(směny, docházka, zaměstnanci) spravujte v aplikaci; admin slouží
hlavně k účtům, skupinám, číselníkům a auditu.

## Nápověda

HTML nápověda je ve složce `help/`. Po změně stránek přegenerujte index:

```powershell
.\.venv\Scripts\python.exe scripts\build_help_index.py
```

## Ověření

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe scripts\check_file_lengths.py
.\.venv\Scripts\python.exe manage.py test
```

## Struktura

- `config/settings/` – base, dev, production
- `apps/accounts` – uživatelé a role
- `apps/core` – přehled, provozní hub, administrace hub, audit, nápověda
- `apps/employees`, `workplaces`, `shifts`, `attendance`, `leave`
- `apps/activities`, `technika`, `documents`
- `help/` – HTML nápověda s fulltextovým vyhledáváním
- `templates/`, `static/mpdmb/` – společné UI (včetně `css/admin.css`)
- `CHANGELOG.md` – historie uživatelsky viditelných verzí
- `scripts/check_file_lengths.py` – limit 1000 řádků
- `scripts/build_help_index.py` – index nápovědy

## Produkce (Windows)

Použijte `config.settings.production`, WSGI/ASGI server za HTTPS
reverse proxy na Windows. Nepoužívejte `runserver` v produkci.
Databáze zůstává SQLite (zálohujte `db.sqlite3`). Detaily doplní
další etapa.
