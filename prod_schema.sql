--
-- PostgreSQL database dump
--

\restrict 5evkejVgQfH58GfTQQ3xhqSZEsNOIFiFWqakzrEftvh0tGNPCeIrVtHtLhdqiTM

-- Dumped from database version 17.6
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

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: generate_application_no(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.generate_application_no() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.application_no IS NULL THEN
        NEW.application_no := 'APP-' || TO_CHAR(NOW(), 'YYYY') || '-' ||
                               LPAD(NEXTVAL('application_no_seq')::TEXT, 6, '0');
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: handle_new_auth_user(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.handle_new_auth_user() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, role, is_active)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    'counselor',
    true
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;


--
-- Name: set_reg_number(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_reg_number() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
declare
  next_seq int;
begin
  if new.reg_number is null then
    select coalesce(max(cast(substring(reg_number from 8) as int)), 0) + 1
      into next_seq
      from public.applicants
      where reg_number ~ ('^DCE' || to_char(now(), 'YYYY') || '[0-9]+$');
    new.reg_number := 'DCE' || to_char(now(), 'YYYY') || lpad(next_seq::text, 3, '0');
  end if;
  return new;
end;
$_$;


--
-- Name: update_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: applicants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applicants (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    reg_number text,
    first_name text NOT NULL,
    last_name text NOT NULL,
    date_of_birth date,
    gender text,
    phone text NOT NULL,
    alternate_phone text,
    email text,
    address_line1 text,
    address_line2 text,
    city text,
    state text DEFAULT 'Tamil Nadu'::text,
    pincode text,
    aadhaar_number text,
    category text,
    community_cert_no text,
    twelfth_school text,
    twelfth_board text,
    twelfth_year integer,
    twelfth_percentage numeric(5,2),
    twelfth_group text,
    pcm_marks numeric(5,2),
    cutoff_marks numeric(5,2),
    entrance_exam text,
    entrance_rank integer,
    entrance_score numeric(7,2),
    parent_name text,
    parent_phone text,
    parent_occupation text,
    annual_income numeric(12,2),
    lead_source text,
    referred_by text,
    assigned_counselor uuid,
    status text DEFAULT 'New Lead'::text,
    priority text DEFAULT 'Normal'::text,
    notes text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    blood_group text,
    father_name text,
    mother_name text,
    father_mobile text,
    address text,
    school_name text,
    hsc_percentage numeric(5,2),
    reference_name text,
    programme_interested text,
    department_interested text,
    doc_status jsonb,
    full_name text,
    mobile text,
    dob date,
    CONSTRAINT applicants_priority_check CHECK ((priority = ANY (ARRAY['High'::text, 'Normal'::text, 'Low'::text])))
);


--
-- Name: application_no_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.application_no_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applications (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    applicant_id uuid NOT NULL,
    application_no text,
    academic_year text DEFAULT '2026-27'::text NOT NULL,
    programme text NOT NULL,
    department text NOT NULL,
    branch text,
    preferred_hostel boolean DEFAULT false,
    preferred_transport boolean DEFAULT false,
    transport_route text,
    application_stage text DEFAULT 'Draft'::text,
    merit_rank integer,
    allotted_seat_type text,
    remarks text,
    submitted_at timestamp with time zone,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    category text,
    CONSTRAINT applications_allotted_seat_type_check CHECK ((allotted_seat_type = ANY (ARRAY['Management'::text, 'Government'::text, 'NRI'::text, 'Lateral Entry'::text, 'Spot'::text]))),
    CONSTRAINT applications_programme_check CHECK ((programme = ANY (ARRAY['B.E.'::text, 'B.Tech'::text, 'M.E.'::text, 'M.Tech'::text, 'MBA'::text, 'MCA'::text])))
);


--
-- Name: call_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_schedules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    lead_id uuid,
    scheduled_by text,
    scheduled_time timestamp without time zone,
    reminder_sent boolean DEFAULT false,
    status text DEFAULT 'Pending'::text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: campus_visits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campus_visits (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    lead_id uuid,
    visit_date date,
    visited_by text,
    departments_seen text,
    outcome text,
    notes text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: counseling_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.counseling_sessions (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    applicant_id uuid NOT NULL,
    application_id uuid,
    counselor_id uuid NOT NULL,
    session_type text NOT NULL,
    session_date timestamp with time zone DEFAULT now() NOT NULL,
    duration_mins integer,
    topics_discussed text[],
    outcome text,
    next_action text,
    next_action_date date,
    notes text,
    mode text DEFAULT 'In-Person'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT counseling_sessions_mode_check CHECK ((mode = ANY (ARRAY['In-Person'::text, 'Remote'::text]))),
    CONSTRAINT counseling_sessions_outcome_check CHECK ((outcome = ANY (ARRAY['Interested'::text, 'Not Interested'::text, 'Need More Time'::text, 'Documents Requested'::text, 'Fee Discussed'::text, 'Confirmed'::text, 'Dropped'::text, 'Callback Scheduled'::text, 'Other'::text]))),
    CONSTRAINT counseling_sessions_session_type_check CHECK ((session_type = ANY (ARRAY['Walk-in'::text, 'Phone Call'::text, 'Video Call'::text, 'WhatsApp'::text, 'Email'::text, 'Home Visit'::text, 'School Visit'::text, 'Camp'::text, 'Follow-up'::text])))
);


--
-- Name: document_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_types (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    is_required boolean DEFAULT true,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true
);


--
-- Name: fee_payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fee_payments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    applicant_id uuid NOT NULL,
    fee_component text NOT NULL,
    amount numeric(10,2) NOT NULL,
    payment_mode text NOT NULL,
    payment_date date DEFAULT CURRENT_DATE NOT NULL,
    receipt_no text,
    academic_year text DEFAULT '2026-27'::text,
    remarks text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: follow_ups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.follow_ups (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    applicant_id uuid,
    assigned_to uuid,
    created_by uuid,
    title text NOT NULL,
    description text,
    follow_up_type text NOT NULL,
    priority text DEFAULT 'Normal'::text,
    due_date timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    status text DEFAULT 'Pending'::text,
    outcome_notes text,
    reminder_sent boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    notes text
);


--
-- Name: followups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.followups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    lead_id uuid,
    called_by text,
    call_date date,
    call_time text,
    response text,
    notes text,
    next_followup_date date,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: hostel_allotments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hostel_allotments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    applicant_id uuid NOT NULL,
    block_name text NOT NULL,
    room_number text NOT NULL,
    room_type text DEFAULT 'Double'::text,
    allotment_date date DEFAULT CURRENT_DATE,
    academic_year text DEFAULT '2026-27'::text,
    status text DEFAULT 'Active'::text,
    remarks text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    phone text NOT NULL,
    email text,
    school text,
    district text,
    marks numeric,
    course_interest text,
    parent_name text,
    parent_occupation text,
    source text,
    status text DEFAULT 'New'::text,
    score integer DEFAULT 0,
    assigned_to text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: lookup_values; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lookup_values (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    type text NOT NULL,
    value text NOT NULL,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: scholarships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scholarships (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    applicant_id uuid NOT NULL,
    scholarship_type text NOT NULL,
    amount numeric(10,2) DEFAULT 0,
    academic_year text DEFAULT '2026-27'::text,
    status text DEFAULT 'Applied'::text,
    reference_no text,
    remarks text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.settings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    category text NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: telecallers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.telecallers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    email text,
    phone text,
    department text,
    active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    email text NOT NULL,
    full_name text NOT NULL,
    phone text,
    role text NOT NULL,
    department text,
    is_active boolean DEFAULT true,
    avatar_url text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT users_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'counselor'::text, 'staff'::text, 'viewer'::text])))
);


--
-- Name: applicants applicants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applicants
    ADD CONSTRAINT applicants_pkey PRIMARY KEY (id);


--
-- Name: applicants applicants_reg_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applicants
    ADD CONSTRAINT applicants_reg_number_key UNIQUE (reg_number);


--
-- Name: applications applications_application_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_application_no_key UNIQUE (application_no);


--
-- Name: applications applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_pkey PRIMARY KEY (id);


--
-- Name: call_schedules call_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_schedules
    ADD CONSTRAINT call_schedules_pkey PRIMARY KEY (id);


--
-- Name: campus_visits campus_visits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campus_visits
    ADD CONSTRAINT campus_visits_pkey PRIMARY KEY (id);


--
-- Name: counseling_sessions counseling_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.counseling_sessions
    ADD CONSTRAINT counseling_sessions_pkey PRIMARY KEY (id);


--
-- Name: document_types document_types_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_types
    ADD CONSTRAINT document_types_name_key UNIQUE (name);


--
-- Name: document_types document_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_types
    ADD CONSTRAINT document_types_pkey PRIMARY KEY (id);


--
-- Name: fee_payments fee_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_payments
    ADD CONSTRAINT fee_payments_pkey PRIMARY KEY (id);


--
-- Name: follow_ups follow_ups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.follow_ups
    ADD CONSTRAINT follow_ups_pkey PRIMARY KEY (id);


--
-- Name: followups followups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followups
    ADD CONSTRAINT followups_pkey PRIMARY KEY (id);


--
-- Name: hostel_allotments hostel_allotments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hostel_allotments
    ADD CONSTRAINT hostel_allotments_pkey PRIMARY KEY (id);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: lookup_values lookup_values_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lookup_values
    ADD CONSTRAINT lookup_values_pkey PRIMARY KEY (id);


--
-- Name: lookup_values lookup_values_type_value_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lookup_values
    ADD CONSTRAINT lookup_values_type_value_key UNIQUE (type, value);


--
-- Name: scholarships scholarships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scholarships
    ADD CONSTRAINT scholarships_pkey PRIMARY KEY (id);


--
-- Name: settings settings_category_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_category_key_key UNIQUE (category, key);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (id);


--
-- Name: telecallers telecallers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telecallers
    ADD CONSTRAINT telecallers_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_applicants_counselor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applicants_counselor ON public.applicants USING btree (assigned_counselor);


--
-- Name: idx_applicants_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applicants_status ON public.applicants USING btree (status);


--
-- Name: idx_applications_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_stage ON public.applications USING btree (application_stage);


--
-- Name: idx_fee_payments_applicant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fee_payments_applicant ON public.fee_payments USING btree (applicant_id);


--
-- Name: idx_follow_ups_assigned; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_follow_ups_assigned ON public.follow_ups USING btree (assigned_to, status);


--
-- Name: idx_follow_ups_due_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_follow_ups_due_date ON public.follow_ups USING btree (due_date);


--
-- Name: idx_follow_ups_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_follow_ups_type ON public.follow_ups USING btree (follow_up_type);


--
-- Name: idx_hostel_applicant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hostel_applicant ON public.hostel_allotments USING btree (applicant_id);


--
-- Name: idx_scholarships_applicant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scholarships_applicant ON public.scholarships USING btree (applicant_id);


--
-- Name: idx_sessions_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sessions_date ON public.counseling_sessions USING btree (session_date);


--
-- Name: fee_payments fee_payments_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER fee_payments_updated_at BEFORE UPDATE ON public.fee_payments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: hostel_allotments hostel_allotments_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER hostel_allotments_updated_at BEFORE UPDATE ON public.hostel_allotments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: scholarships scholarships_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER scholarships_updated_at BEFORE UPDATE ON public.scholarships FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: applications set_application_no; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER set_application_no BEFORE INSERT ON public.applications FOR EACH ROW EXECUTE FUNCTION public.generate_application_no();


--
-- Name: applicants trg_applicants_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_applicants_updated_at BEFORE UPDATE ON public.applicants FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: applications trg_applications_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON public.applications FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: follow_ups trg_followups_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_followups_updated_at BEFORE UPDATE ON public.follow_ups FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: applicants trg_reg_number; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_reg_number BEFORE INSERT ON public.applicants FOR EACH ROW EXECUTE FUNCTION public.set_reg_number();


--
-- Name: counseling_sessions trg_sessions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_sessions_updated_at BEFORE UPDATE ON public.counseling_sessions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: applicants applicants_assigned_counselor_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applicants
    ADD CONSTRAINT applicants_assigned_counselor_fkey FOREIGN KEY (assigned_counselor) REFERENCES public.users(id);


--
-- Name: applicants applicants_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applicants
    ADD CONSTRAINT applicants_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: applications applications_applicant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_applicant_id_fkey FOREIGN KEY (applicant_id) REFERENCES public.applicants(id) ON DELETE CASCADE;


--
-- Name: applications applications_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: call_schedules call_schedules_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_schedules
    ADD CONSTRAINT call_schedules_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id);


--
-- Name: campus_visits campus_visits_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campus_visits
    ADD CONSTRAINT campus_visits_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id);


--
-- Name: counseling_sessions counseling_sessions_applicant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.counseling_sessions
    ADD CONSTRAINT counseling_sessions_applicant_id_fkey FOREIGN KEY (applicant_id) REFERENCES public.applicants(id) ON DELETE CASCADE;


--
-- Name: counseling_sessions counseling_sessions_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.counseling_sessions
    ADD CONSTRAINT counseling_sessions_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.applications(id);


--
-- Name: counseling_sessions counseling_sessions_counselor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.counseling_sessions
    ADD CONSTRAINT counseling_sessions_counselor_id_fkey FOREIGN KEY (counselor_id) REFERENCES public.users(id);


--
-- Name: fee_payments fee_payments_applicant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fee_payments
    ADD CONSTRAINT fee_payments_applicant_id_fkey FOREIGN KEY (applicant_id) REFERENCES public.applicants(id) ON DELETE CASCADE;


--
-- Name: follow_ups follow_ups_applicant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.follow_ups
    ADD CONSTRAINT follow_ups_applicant_id_fkey FOREIGN KEY (applicant_id) REFERENCES public.applicants(id) ON DELETE CASCADE;


--
-- Name: follow_ups follow_ups_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.follow_ups
    ADD CONSTRAINT follow_ups_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.users(id);


--
-- Name: follow_ups follow_ups_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.follow_ups
    ADD CONSTRAINT follow_ups_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: followups followups_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.followups
    ADD CONSTRAINT followups_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id);


--
-- Name: hostel_allotments hostel_allotments_applicant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hostel_allotments
    ADD CONSTRAINT hostel_allotments_applicant_id_fkey FOREIGN KEY (applicant_id) REFERENCES public.applicants(id) ON DELETE CASCADE;


--
-- Name: scholarships scholarships_applicant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scholarships
    ADD CONSTRAINT scholarships_applicant_id_fkey FOREIGN KEY (applicant_id) REFERENCES public.applicants(id) ON DELETE CASCADE;


--
-- Name: users Admins can read all users; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Admins can read all users" ON public.users FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.users users_1
  WHERE ((users_1.id = auth.uid()) AND (users_1.role = 'admin'::text)))));


--
-- Name: counseling_sessions Counselors manage own sessions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Counselors manage own sessions" ON public.counseling_sessions USING (((counselor_id = auth.uid()) OR (EXISTS ( SELECT 1
   FROM public.users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text])))))));


--
-- Name: applicants Counselors see assigned applicants; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Counselors see assigned applicants" ON public.applicants USING (((assigned_counselor = auth.uid()) OR (EXISTS ( SELECT 1
   FROM public.users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text])))))));


--
-- Name: applications Staff can manage applications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Staff can manage applications" ON public.applications USING ((EXISTS ( SELECT 1
   FROM public.users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text, 'counselor'::text]))))));


--
-- Name: users Users can read own record; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read own record" ON public.users FOR SELECT USING ((auth.uid() = id));


--
-- Name: follow_ups Users manage own follow-ups; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users manage own follow-ups" ON public.follow_ups USING (((assigned_to = auth.uid()) OR (created_by = auth.uid()) OR (EXISTS ( SELECT 1
   FROM public.users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text])))))));


--
-- Name: call_schedules allow_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY allow_all ON public.call_schedules USING (true) WITH CHECK (true);


--
-- Name: campus_visits allow_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY allow_all ON public.campus_visits USING (true) WITH CHECK (true);


--
-- Name: followups allow_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY allow_all ON public.followups USING (true) WITH CHECK (true);


--
-- Name: leads allow_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY allow_all ON public.leads USING (true) WITH CHECK (true);


--
-- Name: telecallers allow_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY allow_all ON public.telecallers USING (true) WITH CHECK (true);


--
-- Name: applicants; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.applicants ENABLE ROW LEVEL SECURITY;

--
-- Name: applicants applicants_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY applicants_all ON public.applicants USING (true) WITH CHECK (true);


--
-- Name: applications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;

--
-- Name: applications applications_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY applications_all ON public.applications USING (true) WITH CHECK (true);


--
-- Name: call_schedules; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.call_schedules ENABLE ROW LEVEL SECURITY;

--
-- Name: campus_visits; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.campus_visits ENABLE ROW LEVEL SECURITY;

--
-- Name: counseling_sessions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.counseling_sessions ENABLE ROW LEVEL SECURITY;

--
-- Name: counseling_sessions counseling_sessions_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY counseling_sessions_all ON public.counseling_sessions USING (true) WITH CHECK (true);


--
-- Name: document_types document_types_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY document_types_all ON public.document_types USING (true) WITH CHECK (true);


--
-- Name: fee_payments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.fee_payments ENABLE ROW LEVEL SECURITY;

--
-- Name: fee_payments fee_payments_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY fee_payments_all ON public.fee_payments USING (true) WITH CHECK (true);


--
-- Name: follow_ups; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.follow_ups ENABLE ROW LEVEL SECURITY;

--
-- Name: follow_ups follow_ups_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY follow_ups_all ON public.follow_ups USING (true) WITH CHECK (true);


--
-- Name: followups; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.followups ENABLE ROW LEVEL SECURITY;

--
-- Name: hostel_allotments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.hostel_allotments ENABLE ROW LEVEL SECURITY;

--
-- Name: hostel_allotments hostel_allotments_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY hostel_allotments_all ON public.hostel_allotments USING (true) WITH CHECK (true);


--
-- Name: leads; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

--
-- Name: lookup_values lookup_values_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lookup_values_all ON public.lookup_values USING (true) WITH CHECK (true);


--
-- Name: scholarships; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.scholarships ENABLE ROW LEVEL SECURITY;

--
-- Name: scholarships scholarships_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY scholarships_all ON public.scholarships USING (true) WITH CHECK (true);


--
-- Name: settings settings_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY settings_all ON public.settings USING (true) WITH CHECK (true);


--
-- Name: telecallers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.telecallers ENABLE ROW LEVEL SECURITY;

--
-- Name: users users_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_all ON public.users USING (true) WITH CHECK (true);


--
-- Name: users users_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_insert ON public.users FOR INSERT WITH CHECK (true);


--
-- Name: users users_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_read ON public.users FOR SELECT USING (true);


--
-- Name: users users_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_update ON public.users FOR UPDATE USING ((auth.uid() = id));


--
-- PostgreSQL database dump complete
--

\unrestrict 5evkejVgQfH58GfTQQ3xhqSZEsNOIFiFWqakzrEftvh0tGNPCeIrVtHtLhdqiTM

