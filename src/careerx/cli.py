import typer

from careerx.services.profile_service import ProfileService
from careerx.builders.resume_builder import ResumeBuilder
from careerx.builders.job_description_parser import JobDescriptionParser



app = typer.Typer()


@app.callback()
def main():
    
    pass


@app.command()
def parse_jd():
    jd = "Your job description here"
    parser = JobDescriptionParser()
    job_description = parser.parse(jd)
    
    print(job_description.model_dump_json(indent=4))
    
    
    generic_resume = ProfileService().load_profile()
    
    tailored_resume = ResumeBuilder().build(resume=generic_resume, job_description=job_description)
    
    print(tailored_resume.model_dump_json(indent=4))

@app.command()
def version() -> None:
    typer.echo("CareerX v0.1.0")
