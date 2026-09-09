\restrict dbmate

-- Dumped from database version 17.11
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: headlines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.headlines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ticker text NOT NULL,
    title text NOT NULL,
    url text NOT NULL,
    category text NOT NULL,
    provider text NOT NULL,
    raw_content text,
    published_at timestamp with time zone NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT headlines_category_check CHECK ((category = ANY (ARRAY['news'::text, 'filing'::text])))
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: headlines headlines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.headlines
    ADD CONSTRAINT headlines_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: headlines_ticker_published_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX headlines_ticker_published_at_idx ON public.headlines USING btree (ticker, published_at DESC);


--
-- Name: headlines_url_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX headlines_url_idx ON public.headlines USING btree (url);


--
-- PostgreSQL database dump complete
--

\unrestrict dbmate


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('20260909125433');
