from sqlalchemy.orm import Session
from db.models.literature_model import Literature


def save_merged_to_db(df, db: Session, project_id: int):
    """
    Saves literature into DB
    Rules:
    - First-ever PMID per project → is_unique = True
    - Any repeat PMID (DB or same run) → is_unique = False
    """

    inserted = 0

    # 1️ PMIDs already present in DB
    existing_pmids = {
        r[0]
        for r in db.query(Literature.article_id)
        .filter(Literature.project_id == project_id)
        .all()
    }

    # 2️ Track PMIDs within THIS run
    seen_in_run = set()

    for _, row in df.iterrows():
        article_id = str(row.get("article_id"))

        if article_id in existing_pmids or article_id in seen_in_run:
            is_unique = False
        else:
            is_unique = True

        record = Literature(
            project_id=project_id,
            article_id=article_id,
            keyword_id=row.get("keyword_id"),
            source=row.get("source", "PubMed"),

            title=row.get("title"),
            abstract=row.get("abstract"),

            journal=row.get("journal"),
            publication_year=row.get("publication_year"),

            author=row.get("author", ""),
            publication_type=row.get("publication_type"),

            doi=row.get("doi"),
            article_url=row.get("article_url"),

            is_unique=is_unique
        )

        db.add(record)
        inserted += 1

        # Mark as seen
        seen_in_run.add(article_id)

    db.commit()
    return inserted
