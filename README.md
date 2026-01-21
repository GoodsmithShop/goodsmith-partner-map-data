Goodsmith Partner Map

Zweck

Die Goodsmith Partner Map dient dazu, Endkund:innen passende Goodsmith-Partner in ihrer Nähe zu finden und direkt zu kontaktieren. Gleichzeitig macht sie den Mehrwert der Listung für Partner sichtbar (Sichtbarkeit, Kontaktanfragen, Aktivitätsbadge).

Die Lösung ist bewusst statisch + robust aufgebaut: Daten werden regelmäßig per GitHub Action generiert und als JSON ausgeliefert. Dadurch ist die Map schnell, ausfallsicher und API-schonend.

⸻

Architektur – Überblick

Datenfluss:

Shopify (Customers + Metafelder)
→ GitHub Action (Daily Build)
→ partners.json
→ Frontend (Leaflet Map + Liste)

Technologien:
	•	Shopify Admin GraphQL API
	•	GitHub Actions (Scheduled Build)
	•	Python (Data Build + Klassifizierung)
	•	Leaflet + MarkerCluster
	•	Vanilla JS + CSS

⸻

GitHub Workflow

Name: Daily partner map build

Trigger:
	•	automatisch täglich um 03:00 UTC
	•	manuell via workflow_dispatch

Verhalten:
	•	lädt Partnerdaten aus Shopify
	•	reichert sie mit Geokoordinaten an (inkl. Cache)
	•	klassifiziert Partner (Badge)
	•	schreibt partners.json + geocache.json
	•	commit & push nur bei Änderungen

Dadurch entstehen keine unnötigen Commits.

⸻

Shopify-Datenbasis

Verwendete Customer-Metafelder

Zweck	Namespace / Key
Listung aktiv	customer_fields.listung
Standort	plz_listug, stadt_listung, land_listung
Anzeigename	anzeigename
Ausbildung	ausbildung
Services	gs_hufschuh, gs_klebebeschlag
Website	website / webseite / url / homepage
Bevorzugter Kontakt	bevorzugte_kontaktaufnahme_1

Manuelle Sperre
	•	listung = true → Partner wird gelistet
	•	listung = false oder leer → Partner wird nicht in partners.json aufgenommen

➡️ Keine Frontend-Logik nötig, Sperre erfolgt vollständig im Build-Script.

⸻

Badge-Logik (Partner-Klassifizierung)

Ziel: einfach, verständlich, datenschutzfreundlich

Aktuelle Regeln

Status	Bedingung
Neu dabei	0 Bestellungen insgesamt
Top Partner	≥ 5 Bestellungen in den letzten ~10 Monaten
Aktiver Partner	1–4 Bestellungen in den letzten ~10 Monaten
Gelegentlich aktiv	Bestellungen vorhanden, aber keine in den letzten ~10 Monaten

Wichtig:
	•	Keine Anzeige von Bestellzahlen oder Zeitpunkten
	•	Nur qualitative Einordnung
	•	Tooltip erklärt Bedeutung

⸻

Frontend-Funktionen

Suche
	•	PLZ / Adresse
	•	Radius (km)
	•	Filter: Hufschuh / Klebebeschlag
	•	Optional: aktueller Standort (Browser-Geolocation)

Darstellung
	•	Kartenansicht (Leaflet)
	•	Listenansicht
	•	Mobile Tabs (Map / Liste)
	•	Clustering bei vielen Partnern
	•	Marker mit Goodsmith-Icon

Partnerkarte
	•	Anzeigename
	•	Ausbildung (optional)
	•	Standort
	•	Aktivitäts-Badge mit Tooltip
	•	Kontakt:
	•	Telefon
	•	E-Mail (vorbefüllt, Hinweis auf Goodsmith Map)
	•	WhatsApp (falls bevorzugt)
	•	Website
	•	Entfernung zum Suchort
	•	„Problem melden“-Feedback

⸻

Datenschutz & UX-Entscheidungen
	•	Keine Anzeige von:
	•	Umsätzen
	•	Bestellanzahlen
	•	Bestelldaten
	•	Klassifizierung bewusst vage
	•	Tooltips rein erklärend
	•	WhatsApp & E-Mail Texte enthalten Hinweis auf Goodsmith-Partnerkarte

⸻

Wartung & Weiterentwicklung

Einfach anpassbar
	•	Badge-Logik: classify_badge() im Build-Script
	•	Marker-Größe: iconSize im Frontend
	•	Cluster-Verhalten: markerClusterGroup-Optionen

Mögliche nächste Schritte
	•	Erweiterte Partner-Bewertung (CRM-Inputs)
	•	Hervorhebung empfohlener Partner
	•	Analytics (Klicks, Kontaktaufnahmen)
	•	Admin-UI für Sperren & Tags

⸻

TL;DR

Die Partner Map ist:
	•	schnell
	•	wartungsarm
	•	skalierbar
	•	datenschutzkonform

und verbindet echten Kundennutzen mit klarem Mehrwert für Partner.
