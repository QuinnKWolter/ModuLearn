from types import SimpleNamespace
from django.test import SimpleTestCase
from modulearn.learning.services.recommendation_types import activity_kind, recommendation_tier


def module(provider='', kind='', label='', url=''):
    return SimpleNamespace(provider_id=provider, platform_name=label, content_url=url,
                           content_data={'catalog': {'metadata': {'identity': {'type': kind}}}})


class RecommendationTypesTests(SimpleTestCase):
    def test_actual_types_override_old_labels(self):
        self.assertEqual(activity_kind(module('quizjet', 'PredictingFinalResult', 'Completion Problems')), 'tracing')
        self.assertEqual(activity_kind(module('cupcake', 'FreeCodingProblems')), 'coding')
        self.assertEqual(activity_kind(module('cupcake', 'CodeCompletionProblem')), 'completion')
        self.assertEqual(activity_kind(module('cupcake', 'CodeConstruction')), 'worked_example')
        self.assertEqual(activity_kind(module('pcex_ch', 'CodeConstruction')), 'completion')

    def test_tier_matrix_and_unknown_fallback(self):
        targets = [module('pcex_ch'), module('pcex'), module('animatedexamples'), module('quizjet')]
        for source, expected in [(module('pcrs'), ['recommended','recommended','similar','similar']),
                                 (module('pcex_ch'), ['similar','recommended','similar','similar']),
                                 (module('quizjet'), ['similar','similar','recommended','similar']),
                                 (module('unknown'), ['similar']*4)]:
            self.assertEqual([recommendation_tier(source, target) for target in targets], expected)

    def test_metadata_less_cupcake_and_unknown_are_not_title_guesses(self):
        self.assertEqual(activity_kind(module('cupcake', url='https://adapt2.sis.pitt.edu/cupcake/#/activities/x-code-completion.yaml?protocol=splice')), 'completion')
        self.assertEqual(activity_kind(module('cupcake')), 'other')
        self.assertEqual(activity_kind(module('pcrs', label='Tracing Problems')), 'tracing')
