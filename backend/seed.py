from sqlalchemy import select
from .db import Job, Session, ingest

def seed():
    with Session.begin() as s:
        if s.scalar(select(Job.key).limit(1)):
            return
        rows = [
            ('BMW', 'Mechanical Design Engineer', 'Munich', 76, 'Shortlisted', 'Several years', 'B1', 'Looks like a good fit. Check team and recent projects.'),
            ('Airbus', 'Systems Engineer (A320)', 'Hamburg', 74, 'Shortlisted', 'Several years', 'B2', 'Review job details and prepare questions.'),
            ('N3', 'Simulation Engineer', 'Arnstadt', 68, 'Shortlisted', '2–5 years', 'B1', 'Interesting role in simulation. Check required tools and skills.'),
            ('MTU Aero Engines', 'Design Engineer', 'Munich', 73, 'Applied', 'Several years', 'Fluent', 'Prepare portfolio.'),
            ('Lufthansa Technik', 'Aircraft Maintenance Engineer', 'Hamburg', 69, 'Applied', 'Several years', 'B2', 'Application submitted. Keep an eye on the portal.'),
            ('Airbus', 'Manufacturing Engineer', 'Munich', 66, 'Applied', '2–5 years', 'B1', 'Applied via company portal. Follow up in two weeks.'),
            ('Lufthansa Technik', 'Structural Design Engineer', 'Hamburg', 75, 'Interview', 'Several years', 'B2', 'First interview completed. Preparing for technical round.'),
            ('BMW', 'Validation Engineer', 'Munich', 71, 'Interview', 'Several years', 'B2', 'Technical interview scheduled. Review key topics.'),
            ('MTU Aero Engines', 'Quality Engineer', 'Munich', 72, 'New', '2+ years', 'Good', ''),
            ('Airbus', 'Manufacturing Quality Engineer', 'Hamburg', 70, 'New', 'Not stated', 'Not stated', ''),
            ('N3', 'Process Engineer', 'Arnstadt', 64, 'New', 'Several years', 'Desirable', ''),
            ('BMW', 'Production Engineer', 'Munich', 67, 'New', '3+ years', 'B2', ''),
        ]
        for i, (company, title, location, score, status, experience, german, notes) in enumerate(rows):
            ingest(s, [dict(id=f'demo-{i}', title=title, company=company, location=location,
                total_score=score, experience_required=experience, german_required=german,
                experience_min_years=2 if experience in ('2+ years', '2–5 years') else 3 if experience == '3+ years' else None,
                source_site='Demo', source='CS', job_url='', description='Illustrative role for testing your workflow. These are not live job listings.',
                experience_evidence=f'Sample: {experience} of experience.', german_evidence=f'Sample German wording: {german}.')])
            s.flush()
            job = s.scalar(select(Job).where(Job.data['id'].as_string() == f'demo-{i}'))
            job.status, job.notes = status, notes
