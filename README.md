# RFP Sentinel

**An AI co-pilot that helps government tenders get evaluated fairly, quickly, and transparently.**

<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/c6677a02-f9ad-4b59-8cb5-6d8e3ae86bc3" />
<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/b564e111-460e-4daf-b8b2-9016c4bbf387" />
<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/8c3c932d-399b-45ed-9eeb-8afdc16c7202" />
<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/4b6bdeb2-1fe3-4b24-8724-e1f7fb741acc" />

## What is this ?
In India, government departments buy things like laptops or office equipment through an official online marketplace called **GeM**. A department publishes a tender (a document listing what they need and who's allowed to bid), companies submit bids, and someone has to fairly compare every bid against the rules and pick a winner.

**RFP Sentinel is software that helps with both sides of that process.** A government buyer uploads their tender, and the system automatically checks it against real government procurement rules — flagging anything that looks non-compliant *before* it goes public, with a citation to the exact rule, so a human can review it in seconds instead of reading pages of regulation. Once bids come in, it checks each one against the tender's own requirements and produces a ranked, explainable result — but it never picks the final winner on its own. A person always makes that call.

**Why this matters**: almost every AI tool in this space is built for the *company bidding* on a tender — helping them write a better response. RFP Sentinel is built for the other side: the government buyer who has to check the tender is fair and then evaluate what comes back, honestly and defensibly. That's the harder, less-served problem, and it's the whole point of this project.

## Who uses it

The platform has three kinds of users:

- **Buyers** upload a tender, review anything the system flags, publish it, and — once bidding closes — review the ranked results.
- **Bidders** (sellers) can browse open tenders without even logging in, see exactly what documents they need to submit, and apply.
- **Admins** oversee the whole system: keeping the rulebook of government regulations up to date, managing accounts, and auditing any tender that was published despite a flagged issue.

## What makes it worth a second look

- **Every automated flag comes with a citation** to the actual rule it's based on — nothing is a black-box opinion.
- **A human always has the final say.** The system suggests and ranks; it never auto-selects a winner or auto-rejects a tender.
- **Sealed bidding, done properly.** A bidder's price is uploaded as a sealed document and literally cannot be read by the system until the technical review is fully finished — mirroring how real government tenders are legally required to work.
- **Built and checked against real government tender documents** throughout, not made-up test data.

## Tech, briefly

Python (FastAPI) backend, React frontend, a local/open-source AI model for document understanding, and Postgres + Qdrant for storage.

## Try it yourself

**Prerequisites**: Docker, Python 3.11+, Node.js 20+, and [Ollama](https://ollama.com) (local or remote) with `llama3.2:3b` and `nomic-embed-text` pulled.

```
cp .env.example .env
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Then, in three separate terminals:
```
docker compose up -d                            # infrastructure (Postgres + Qdrant)
./venv/bin/uvicorn backend.main:app --reload     # backend — wait for "Application startup complete"
cd frontend && npm run dev                       # frontend — open http://localhost:5173
```

Browsing published tenders needs no login. Buyer/bidder/admin each have their own login page from the homepage.

## Want more detail?

See [`ROADMAP.md`](ROADMAP.md) for what's intentionally not built yet, and why.
