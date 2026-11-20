-- Example only. Snowflake is a PAID service and needs your own account; the data leaves your computer (verify current Snowflake docs).
-- Never load client data without the client's permission. Names below are placeholders.
CREATE DATABASE IF NOT EXISTS YUKI_EXAMPLE;
CREATE SCHEMA IF NOT EXISTS YUKI_EXAMPLE.EXPORT;
CREATE OR REPLACE FILE FORMAT YUKI_EXAMPLE.EXPORT.CSV_FMT TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"';
CREATE OR REPLACE STAGE YUKI_EXAMPLE.EXPORT.YUKI_STAGE FILE_FORMAT = YUKI_EXAMPLE.EXPORT.CSV_FMT;
-- Run PUT from SnowSQL or another client that supports it (path = your export folder):
-- PUT file:///ABSOLUTE/PATH/TO/export/yuki-kpis.csv @YUKI_EXAMPLE.EXPORT.YUKI_STAGE AUTO_COMPRESS=TRUE;
CREATE OR REPLACE TABLE YUKI_EXAMPLE.EXPORT.KPIS (
  administratie STRING, periode_van DATE, periode_tot DATE, peildatum DATE, kpi STRING, waarde FLOAT, eenheid STRING);
COPY INTO YUKI_EXAMPLE.EXPORT.KPIS FROM @YUKI_EXAMPLE.EXPORT.YUKI_STAGE/yuki-kpis.csv.gz;
