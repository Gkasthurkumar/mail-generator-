"""
portfolio.py
------------
Wraps a small ChromaDB collection built from resource/my_portfolio.csv
(columns: Techstack, Links). Given a list of skills pulled from a job
description, it returns the most relevant portfolio links to reference
in the generated cold email.
"""

import uuid
import pandas as pd
import chromadb


class Portfolio:
    def __init__(self, file_path: str = "resource/my_portfolio.csv"):
        self.file_path = file_path
        self.data = pd.read_csv(file_path)
        self.chroma_client = chromadb.PersistentClient(path="vectorstore")
        self.collection = self.chroma_client.get_or_create_collection(name="portfolio")

    def load_portfolio(self):
        """Populate the Chroma collection once; safe to call every run."""
        if not self.collection.count():
            for _, row in self.data.iterrows():
                self.collection.add(
                    documents=[row["Techstack"]],
                    metadatas=[{"links": row["Links"]}],
                    ids=[str(uuid.uuid4())],
                )

    def query_links(self, skills, n_results: int = 2):
        """
        Parameters
        ----------
        skills : list[str]
            Skills extracted from the job description.
        n_results : int
            How many portfolio matches to pull per query.

        Returns
        -------
        list[str]
            De-duplicated portfolio links relevant to the given skills.
        """
        if not skills:
            return []

        self.load_portfolio()
        results = self.collection.query(query_texts=skills, n_results=n_results)

        links = set()
        for metadata_group in results.get("metadatas", []):
            for meta in metadata_group:
                if meta and "links" in meta:
                    links.add(meta["links"])
        return list(links)
