import streamlit as st

st.set_page_config(page_title="Technical Plan — Deadlines Tracker", layout="wide")
st.title("Technical Plan")
st.caption("Reference document for infrastructure and deployment planning.")

st.markdown("""
### Code storage
**Current:** Local git repository
**Plan:** Private GitHub repository under company org

---

### Credentials
**Current:** Local .env file on developer machine
**Plan:** Azure App Service environment variables — never hardcoded or committed to git

---

### Authentication
**Current:** Name prompt only, no real login
**Plan:** Microsoft Entra ID via Azure Easy Auth — staff log in with existing company Microsoft accounts, no code changes required

---

### Database
**Current:** Supabase (third-party PostgreSQL service, not used elsewhere in the business)
**Plan:** Azure Database for PostgreSQL or Azure SQL Database — keeps everything within the Microsoft ecosystem, familiar to any company DBA

---

### Deployment
**Current:** Runs locally on one machine
**Plan:** Azure App Service — stateless app, all data in the database, straightforward to deploy and monitor

---

### Data residency
**Current:** Supabase US servers by default
**Plan:** Azure region of our choice, EU available for compliance

---

### Gaps to address before wider rollout
- Enable Row Level Security on the database before sharing the URL broadly
- Notes edits do not currently record who made them
- No log of fixture additions or deletions
""")
