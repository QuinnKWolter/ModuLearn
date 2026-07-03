from __future__ import annotations


AVAILABLE_COURSE_PLUGINS = [
    {
        "key": "guided_sequence",
        "name": "Guided Sequence",
        "summary": "Defaults the course to module-by-module progression where each module unlocks after the previous one is completed.",
    },
    {
        "key": "adaptive_branching",
        "name": "Adaptive Branching",
        "summary": "Unlocks different next modules for each learner based on success, failure, completion, or score rules.",
    },
    {
        "key": "static_recommendations",
        "name": "Static Recommendations",
        "summary": "Prepared module links can feed a recommendation queue after configured triggers.",
    },
    {
        "key": "dynamic_recommendations",
        "name": "Dynamic Recommendations",
        "summary": "Runtime recommendation hooks can suggest modules after failed or low-success work.",
    },
]


def available_course_plugins():
    return AVAILABLE_COURSE_PLUGINS


def normalize_course_plugin_config(config):
    config = config if isinstance(config, dict) else {}
    plugins = config.get("plugins") if isinstance(config.get("plugins"), dict) else {}
    normalized = {"plugins": {}}
    for plugin in AVAILABLE_COURSE_PLUGINS:
        plugin_key = plugin["key"]
        plugin_config = plugins.get(plugin_key) if isinstance(plugins.get(plugin_key), dict) else {}
        normalized["plugins"][plugin_key] = {
            "enabled": bool(plugin_config.get("enabled", False)),
            "settings": plugin_config.get("settings") if isinstance(plugin_config.get("settings"), dict) else {},
        }
    return normalized


def is_course_plugin_enabled(course, plugin_key):
    config = normalize_course_plugin_config(getattr(course, "plugin_config", None))
    return bool(config["plugins"].get(plugin_key, {}).get("enabled"))


def enabled_course_plugins(course):
    config = normalize_course_plugin_config(getattr(course, "plugin_config", None))
    return {
        plugin["key"]: bool(config["plugins"].get(plugin["key"], {}).get("enabled"))
        for plugin in AVAILABLE_COURSE_PLUGINS
    }
