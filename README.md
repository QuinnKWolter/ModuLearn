# ModuLearn

ModuLearn is a lightweight Django-based web application designed for seamless integration with **Canvas LMS** via **LTI 1.3**, **LTI 1.1**, or through standalone use. It allows for the delivery and management of **smart eLearning modules**, including coding challenges, quizzes, and interactive simulations. This app ensures that students can track progress, resume incomplete work, and have their cumulative grades dynamically updated.

## Features

- **LTI 1.3/1.1 Integration**: Securely integrates with Canvas, handling OAuth2 authentication and enabling grade submission via Assignment and Grade Services (AGS).
- **Modular Smart Content**: Handles various types of smart content (e.g., coding problems, quizzes) and tracks student progress across sessions.
- **Progress Tracking**: Students can seamlessly resume incomplete modules, with all progress stored in the database.
- **Cumulative Grading**: Automatically calculates and submits a rolling grade back to Canvas as students complete modules.
- **Standalone Access**: The app can also be accessed independently of Canvas, allowing students to interact with the platform outside the LMS ecosystem.
- **Instructor Tools**: Instructors can import course content from external authoring tools, track student progress, and monitor grades.

## Requirements

- **Python 3.8+**
- **Django 3.2+**
- **SQLite**

## Installation
_etc. etc. TBD_
