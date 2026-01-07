from sqlalchemy.orm import Session
from db.models.literature_results_model import LiteratureResult
from db.models.literature_keywords_model import LiteratureKeyword


def save_merged_to_db(df, db: Session, project_id: str):
    """
    Saves merged PubMed results into literature_results
    - Duplicates allowed
    """

    inserted = 0

    # Map keyword_no → keyword_id
    keyword_map = {
        k.keyword_no: k.id
        for k in db.query(LiteratureKeyword)
        .filter(LiteratureKeyword.project_id == project_id)
        .all()
    }

    for _, row in df.iterrows():
        keyword_id = keyword_map.get(row.get("keyword_no"))

        if not keyword_id:
            continue

        record = LiteratureResult(
            project_id=project_id,
            keyword_id=keyword_id,
            pmid=row.get("pmid"),
            title=row.get("title"),
            abstract=row.get("abstract"),
            journal=row.get("journal"),
            publication_year=row.get("pub_date"),
            authors=row.get("authors", ""),
            source="PubMed"
        )

        db.add(record)
        inserted += 1

    db.commit()
    return inserted
