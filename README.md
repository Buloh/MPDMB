# SYNERA – propojení zaměstnanců, směn, docházky, úkolů a provozu

Verze **0.2.0**. Webová aplikace SYNERA (synergie v jednom systému)
pro provoz parkovacích domů v Mladé Boleslavi.

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

- Na tomto PC: http://127.0.0.1:8000/
- Nápověda: http://127.0.0.1:8000/napoveda/
- Z jiné stanice v síti/VPN: http://<IPv4-počítače>:8000/
- Zdravotní kontrola: http://127.0.0.1:8000/health/

IPv4 zjistěte příkazem `ipconfig`. Port 8000 povolte ve firewallu
jen pro důvěryhodnou síť/VPN.

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
- `apps/accounts` – vlastní model uživatele a role
- `apps/core` – jádro, audit, zdravotní kontrola, nápověda
- `help/` – HTML nápověda s fulltextovým vyhledáváním
- `templates/`, `static/mpdmb/` – společné UI
- `design/` – statický návrh (není runtime aplikace)
- `scripts/check_file_lengths.py` – limit 1000 řádků
- `scripts/build_help_index.py` – index nápovědy

## Produkce (Windows)

Použijte `config.settings.production`, WSGI/ASGI server za HTTPS
reverse proxy na Windows. Nepoužívejte `runserver` v produkci.
Databáze zůstává SQLite (zálohujte `db.sqlite3`). Detaily doplní
další etapa.
