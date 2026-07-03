from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from modulearn.learning.services.course_plugins import normalize_course_plugin_config
from modulearn.learning.services.access_rules import build_unlock_rule

from .models import Course, CourseInstance, Module, ModuleBranchRule, Unit


INTRO_PYTHON_DEMO_KEY = "intro_python"
DEMO_COURSE_TITLE = "Intro to Python - SPLICE Demo Course"
DEMO_COURSE_DESCRIPTION = (
    "A lightweight, fully structured demo course: 10 units, 28 modules, "
    "linked to live SPLICE-delivered JSVEE and CodeCheck resources."
)
ADAPTIVE_BRANCHING_DEMO_KEY = "adaptive_branching"
ADAPTIVE_BRANCHING_DEMO_TITLE = "Adaptive Branching - Demo Course"
ADAPTIVE_BRANCHING_DEMO_DESCRIPTION = (
    "A compact instructor demo showing a correct-answer path and an incorrect-answer remediation path."
)


DEMO_UNITS = [
    {
        "title": "Variables and Operations",
        "description": "Assignment, input/output, and arithmetic - the raw materials every later program is built from.",
        "modules": [
            ("Variable assignment", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_assignment"),
            ("Simple Printing", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-Branches-3"),
            ("Pythagorean hypotenuse", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-FunctionsWithDecisions-1"),
        ],
    },
    {
        "title": "Booleans and Conditionals",
        "description": "Truth values and comparisons, then branching on them with if / elif / else to make programs decide.",
        "modules": [
            ("Boolean logic", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_adl_logic"),
            ("Comparison operators", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_adl_comparison"),
            ("If statement", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_if"),
            ("Chessboard square color", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-Branches-3"),
            ("Quadrant / axis / origin", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-Branches-4"),
        ],
    },
    {
        "title": "Loops",
        "description": "Repetition with while and for, including nested iteration over grids of values.",
        "modules": [
            ("While loop", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_while"),
            ("For loop", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_for"),
            ("Sum of positives (nested loops)", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-LoopingOvertheEntireArray-1"),
        ],
    },
    {
        "title": "Functions",
        "description": "Packaging logic into reusable, parameterized units that return results and call one another.",
        "modules": [
            ("Defining functions", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_function"),
            ("Same sign", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-FunctionsWithDecisions-1"),
        ],
    },
    {
        "title": "Lists, Values and References",
        "description": "Building and manipulating sequences, and understanding how Python shares vs. copies the values inside them.",
        "modules": [
            ("Lists", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_list"),
            ("Sum of positives", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-SumsAveragesProducts-1"),
            ("Max minus min", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-MaximumandMinimum-4"),
            ("Values & references", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_adl_vals_refs1"),
        ],
    },
    {
        "title": "Two-Dimensional Lists",
        "description": "Working with grids: traversing rows and columns, borders, and neighborhoods.",
        "modules": [
            ("Replace negatives with zero", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-LoopingOvertheEntireArray-4"),
            ("Sum of a row or column", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-LoopsAlongaRoworColumn-3"),
        ],
    },
    {
        "title": "Strings",
        "description": "Treating text as data: indexing, searching, and transforming character sequences.",
        "modules": [
            ("Strings", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_adl_strings"),
            ("Longest word", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-StringWords-1"),
            ("Swap first and last char", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-StringsNoLoops-1"),
        ],
    },
    {
        "title": "Dictionaries",
        "description": "Storing and retrieving data by key, and walking structured (nested) records.",
        "modules": [
            ("Dictionaries", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_dict"),
            ("Iterate nested JSON", "Challenge", "CodeCheck", "https://codecheck.io/files/horstmann/codecheck-python-LoopingOvertheEntireArray-1"),
        ],
    },
    {
        "title": "File Handling and Exceptions",
        "description": "Reading and writing external data, and handling the errors that I/O inevitably raises.",
        "modules": [
            ("File I/O", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_file"),
            ("Try / except", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_adl_tryexcept1"),
        ],
    },
    {
        "title": "Classes and Objects",
        "description": "Bundling state and behavior into custom types to model real-world entities.",
        "modules": [
            ("Classes", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_python_class1"),
            ("Objects", "Animated", "JSVEE", "https://acos.cs.vt.edu/html/jsvee/jsvee-python/ae_adl_objects1"),
        ],
    },
]


def _intro_demo_module_specs():
    specs = {}
    for unit_data in DEMO_UNITS:
        for title, kind, platform_name, url in unit_data["modules"]:
            specs[title] = {
                "kind": kind,
                "platform_name": platform_name,
                "provider_id": platform_name.lower(),
                "content_url": url,
            }
    return specs


ADAPTIVE_BRANCHING_MODULES = [
    {
        "title": "Exercise A: Branching Check",
        "description": "Students attempt this scored activity first. A successful outcome unlocks the stretch path; an unsuccessful scored outcome unlocks remediation.",
        "url": "https://codecheck.io/files/horstmann/codecheck-python-Branches-3",
        "platform_name": "CodeCheck",
        "provider_id": "codecheck",
        "is_locked": False,
    },
    {
        "title": "Path B: Stretch Challenge",
        "description": "Unlocked when Exercise A reports a successful/correct outcome.",
        "url": "https://codecheck.io/files/horstmann/codecheck-python-Branches-4",
        "platform_name": "CodeCheck",
        "provider_id": "codecheck",
        "is_locked": True,
    },
    {
        "title": "Path C: Targeted Review",
        "description": "Unlocked when Exercise A reports an unsuccessful/incorrect scored outcome.",
        "url": "https://codecheck.io/files/horstmann/codecheck-python-FunctionsWithDecisions-1",
        "platform_name": "CodeCheck",
        "provider_id": "codecheck",
        "is_locked": True,
    },
    {
        "title": "Wrap-Up Reflection",
        "description": "A short final checkpoint unlocked after either branch path is completed.",
        "url": "https://codecheck.io/files/horstmann/codecheck-python-SumsAveragesProducts-1",
        "platform_name": "CodeCheck",
        "provider_id": "codecheck",
        "is_locked": True,
    },
]


def _repair_intro_python_demo_course(course):
    specs = _intro_demo_module_specs()
    previous_module = None
    modules = (
        Module.objects.filter(unit__course=course)
        .select_related("unit")
        .order_by("unit__order", "unit__id", "order", "id")
    )
    for module in modules:
        spec = specs.get(module.title)
        if spec:
            module.description = f"{spec['kind']}."
            module.content_url = spec["content_url"]
            module.platform_name = spec["platform_name"]
            module.provider_id = spec["provider_id"]
            module.supported_protocols = ["splice"]
            module.content_data = {
                **(module.content_data or {}),
                "demo_course": "intro-python-splice-v1",
                "activity_kind": spec["kind"],
                "link_status": "live",
            }

        module.is_visible = True
        module.is_locked = previous_module is not None
        module.unlock_rule = build_unlock_rule("module_completed", previous_module.id) if previous_module else {}
        module.save(update_fields=[
            "description",
            "content_url",
            "platform_name",
            "provider_id",
            "supported_protocols",
            "content_data",
            "is_visible",
            "is_locked",
            "unlock_rule",
        ])
        previous_module = module


def _repair_adaptive_branching_demo_course(course):
    modules = list(Module.objects.filter(unit__course=course).order_by("unit__order", "unit__id", "order", "id")[:4])
    if len(modules) < 4:
        return

    for module, module_data in zip(modules, ADAPTIVE_BRANCHING_MODULES):
        module.title = module_data["title"]
        module.description = module_data["description"]
        module.content_url = module_data["url"]
        module.platform_name = module_data["platform_name"]
        module.provider_id = module_data["provider_id"]
        module.supported_protocols = ["splice"]
        module.is_visible = True
        module.is_locked = module_data["is_locked"]
        module.unlock_rule = {}
        module.content_data = {
            **(module.content_data or {}),
            "demo_course": "adaptive-branching-v1",
        }
        module.save(update_fields=[
            "title",
            "description",
            "content_url",
            "platform_name",
            "provider_id",
            "supported_protocols",
            "is_visible",
            "is_locked",
            "unlock_rule",
            "content_data",
        ])

    source, success_target, failure_target, wrap_up = modules
    rule_specs = [
        (source, success_target, ModuleBranchRule.CONDITION_SUCCESS, 10),
        (source, failure_target, ModuleBranchRule.CONDITION_FAILURE, 20),
        (success_target, wrap_up, ModuleBranchRule.CONDITION_COMPLETED, 30),
        (failure_target, wrap_up, ModuleBranchRule.CONDITION_COMPLETED, 40),
    ]
    for source_module, target_module, condition_type, priority in rule_specs:
        rule, _created = ModuleBranchRule.objects.update_or_create(
            course=course,
            source_module=source_module,
            target_module=target_module,
            condition_type=condition_type,
            defaults={"priority": priority, "active": True},
        )
        if not rule.active or rule.priority != priority:
            rule.active = True
            rule.priority = priority
            rule.save(update_fields=["active", "priority"])


def repair_demo_courses_for_instructor(instructor):
    for course in Course.objects.filter(instructors=instructor, title=DEMO_COURSE_TITLE):
        _repair_intro_python_demo_course(course)
    for course in Course.objects.filter(instructors=instructor, title=ADAPTIVE_BRANCHING_DEMO_TITLE):
        _repair_adaptive_branching_demo_course(course)


def create_intro_python_demo_course(instructor):
    """Create an isolated demo course/session for the requesting instructor."""
    suffix = uuid.uuid4().hex[:10]
    now = timezone.localtime(timezone.now())
    now_label = f"{now.strftime('%b')} {now.day}, {now.year} {now.strftime('%I:%M %p')}"

    with transaction.atomic():
        course = Course.objects.create(
            id=f"demo-intro-python-{suffix}",
            title=DEMO_COURSE_TITLE,
            description=DEMO_COURSE_DESCRIPTION,
        )
        course.instructors.add(instructor)

        instance = CourseInstance.objects.create(
            course=course,
            group_name=f"Demo Session - {now_label}",
        )
        instance.instructors.add(instructor)

        previous_module = None
        for unit_index, unit_data in enumerate(DEMO_UNITS, start=1):
            unit = Unit.objects.create(
                course=course,
                title=unit_data["title"],
                description=unit_data["description"],
                order=unit_index * 10,
            )
            for module_index, (title, kind, platform_name, url) in enumerate(unit_data["modules"], start=1):
                module = Module.objects.create(
                    unit=unit,
                    title=title,
                    description=f"{kind}.",
                    module_type=Module.MODULE_TYPE_SPLICE_SMART_CONTENT,
                    order=module_index * 10,
                    is_visible=True,
                    is_locked=previous_module is not None,
                    unlock_rule=build_unlock_rule("module_completed", previous_module.id) if previous_module else {},
                    content_url=url,
                    platform_name=platform_name,
                    provider_id=platform_name.lower(),
                    supported_protocols=["splice"],
                    content_data={
                        "demo_course": "intro-python-splice-v1",
                        "activity_kind": kind,
                        "link_status": "live",
                    },
                )
                previous_module = module

    return course, instance


def instructor_has_intro_python_demo_course(instructor):
    return Course.objects.filter(
        instructors=instructor,
        title=DEMO_COURSE_TITLE,
    ).exists()


def create_adaptive_branching_demo_course(instructor):
    suffix = uuid.uuid4().hex[:10]
    now = timezone.localtime(timezone.now())
    now_label = f"{now.strftime('%b')} {now.day}, {now.year} {now.strftime('%I:%M %p')}"

    with transaction.atomic():
        course = Course.objects.create(
            id=f"demo-adaptive-branching-{suffix}",
            title=ADAPTIVE_BRANCHING_DEMO_TITLE,
            description=ADAPTIVE_BRANCHING_DEMO_DESCRIPTION,
            plugin_config=normalize_course_plugin_config({
                "plugins": {
                    "guided_sequence": {"enabled": True, "settings": {}},
                    "adaptive_branching": {"enabled": True, "settings": {}},
                }
            }),
        )
        course.instructors.add(instructor)

        instance = CourseInstance.objects.create(
            course=course,
            group_name=f"Branching Demo - {now_label}",
        )
        instance.instructors.add(instructor)

        unit = Unit.objects.create(
            course=course,
            title="Adaptive Branching Walkthrough",
            description="A minimal sequence demonstrating personalized next-module unlocks.",
            order=10,
        )

        modules = []
        for module_index, module_data in enumerate(ADAPTIVE_BRANCHING_MODULES, start=1):
            modules.append(Module.objects.create(
                unit=unit,
                title=module_data["title"],
                description=module_data["description"],
                module_type=Module.MODULE_TYPE_SPLICE_SMART_CONTENT,
                order=module_index * 10,
                is_visible=True,
                is_locked=module_data["is_locked"],
                unlock_rule={},
                content_url=module_data["url"],
                platform_name=module_data["platform_name"],
                provider_id=module_data["provider_id"],
                supported_protocols=["splice"],
                content_data={
                    "demo_course": "adaptive-branching-v1",
                    "branch_role": ["source", "success_target", "failure_target", "wrap_up"][module_index - 1],
                },
            ))

        source, success_target, failure_target, wrap_up = modules
        ModuleBranchRule.objects.create(
            course=course,
            source_module=source,
            target_module=success_target,
            condition_type=ModuleBranchRule.CONDITION_SUCCESS,
            priority=10,
        )
        ModuleBranchRule.objects.create(
            course=course,
            source_module=source,
            target_module=failure_target,
            condition_type=ModuleBranchRule.CONDITION_FAILURE,
            priority=20,
        )
        ModuleBranchRule.objects.create(
            course=course,
            source_module=success_target,
            target_module=wrap_up,
            condition_type=ModuleBranchRule.CONDITION_COMPLETED,
            priority=30,
        )
        ModuleBranchRule.objects.create(
            course=course,
            source_module=failure_target,
            target_module=wrap_up,
            condition_type=ModuleBranchRule.CONDITION_COMPLETED,
            priority=40,
        )

    return course, instance


def instructor_has_adaptive_branching_demo_course(instructor):
    return Course.objects.filter(
        instructors=instructor,
        title=ADAPTIVE_BRANCHING_DEMO_TITLE,
    ).exists()


DEMO_COURSE_OPTIONS = [
    {
        "key": INTRO_PYTHON_DEMO_KEY,
        "title": DEMO_COURSE_TITLE,
        "summary": "Full 10-unit SPLICE Python walkthrough with JSVEE and CodeCheck resources.",
        "create": create_intro_python_demo_course,
        "exists": instructor_has_intro_python_demo_course,
    },
    {
        "key": ADAPTIVE_BRANCHING_DEMO_KEY,
        "title": ADAPTIVE_BRANCHING_DEMO_TITLE,
        "summary": "Slim 4-module course with correct and incorrect outcome branches already configured.",
        "create": create_adaptive_branching_demo_course,
        "exists": instructor_has_adaptive_branching_demo_course,
    },
]


def available_demo_course_options(instructor):
    repair_demo_courses_for_instructor(instructor)
    return [
        {key: value for key, value in option.items() if key not in {"create", "exists"}}
        for option in DEMO_COURSE_OPTIONS
        if not option["exists"](instructor)
    ]


def create_demo_course_for_key(instructor, demo_key):
    demo_key = demo_key or INTRO_PYTHON_DEMO_KEY
    for option in DEMO_COURSE_OPTIONS:
        if option["key"] == demo_key:
            if option["exists"](instructor):
                raise ValueError("This demo course already exists for your instructor account.")
            return option["create"](instructor)
    raise ValueError("Unknown demo course type.")
