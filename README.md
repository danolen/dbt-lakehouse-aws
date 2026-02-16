# My Fantasy Baseball Lakehouse & Draft Tool

## Overview

This is a personal data lakehouse and analytics platform built to support my fantasy baseball draft preparation and in-season decision making. Currently built out is a set of draft-ready player rankings and valuations, while the longer-term goal is to grow this into a full end-to-end analytics application with automation, orchestration, and an interactive user interface. This project supports just one engineer/analyst right now (myself), but is designed to be able to scale to support a small team of engineers and analysts, while remaining cost-efficient and lightweight enough for personal use.

---

## Goals & Motivation

- Build hands-on experience with **lakehouse architecture**
- Use **dbt** as the core transformation layer
- Design for **incremental growth** in data volume and complexity
- Create a **real, usable product**, not a toy dataset
- Practice making pragmatic trade-offs around cost, tooling, and scope

Although the current dataset is small, the architecture is designed to scale naturally as new data sources and products are added.

---

## Current Architecture

### Data extraction
- Files downloaded locally. Automation of this process typically violates the Terms & Conditions of the data providers in use.
- Planned future enhancement: Automate extraction of data where allowed
  - Expected tools: Python + Airflow (or similar)

### Storage
- Amazon S3, with year=YYYY/month=MM/day=DD/ partioning logic

### Data Architecture
- Lakehouse in Athena
- External tables defined from raw CSV/TSV files
- All fields are defined as strings, with type casting and normalization handled downstream by dbt
- Partitioning is logical, based on ingestion date, rather than physical, simplifying refreshes

### Transformation
- dbt creates Iceberg tables in Athena
- Medallion-style architecture
  - Source models: Select all columns from external table, add any necessary partition fields, filter to only necessary data
    - Filtering thought process: Even though I may still want to analyze old data later, I only want to surface the most current, up-to-date data for my end product
  - Stage models: Perform any transformations needed to create intermediary tables that should **not** be exposed to future BI tools/apps/analysis
  - Main models: These are the end-product tables that are meant to be consumed by BI tools and apps
- Planned future enhancements:
  - Make further use of incremental materializations
  - Add tests and documentation
  - Make use of variables and macros to make project more modular
  - Simplify model lineage
 
### Draft Tool Application
- Used **Streamlit** to create a web app to be used in a draft
- Mobile- and desktop-friendly interface
- Includes all of my player rankings and valuations for various fantasy baseball contest formats, including projected player stats
- Real-time filtering and sorting
- Access anywhere
- Track which players have/haven't been drafted
  - Use **Amazon DynamoDB** to track and update the drafted status of a player with the click of a button
  - Decouple player drafted status from analytical data
 
### Access control
- IAM roles

### Version Control
- Github

---

## Planned future enhancements

### In-Season Tools
- Another **Streamlit** web app to help with player add/drop decisions, lineup optimization, etc.

### Orchestration
- **Apache Airflow** (or similar)
  - Automate ingestion tasks, dbt builds, app refreshes
  - Support for scheduled and manual ad-hoc refresh workflows
  - Likely to use AWS MWAA or lightweight alternatives, or may start with dbt Cloud orchestration jobs or GitHub Actions

---

## Disclaimer

This project is mainly for personal use and learning purposes. All data sources are accessed via legitimate paid subscriptions if data is not freely available, and are not redistributed.

