(function () {
  async function createCourse(config) {
    var loadingState = document.getElementById('loadingState');
    var errorState = document.getElementById('errorState');
    var errorMessage = document.getElementById('errorMessage');

    if (!config.courseExportUrl) {
      loadingState.classList.add('hidden');
      errorState.classList.remove('hidden');
      errorMessage.textContent = 'No course ID was provided.';
      return;
    }

    try {
      var exportResponse = await fetch(config.courseExportUrl, {
        method: 'GET',
        credentials: 'include',
      });

      if (!exportResponse.ok) {
        throw new Error('Failed to fetch course details: ' + exportResponse.statusText);
      }

      var courseData = await exportResponse.json();
      var backendResponse = await fetch(config.createCourseUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ course_data: courseData }),
      });

      if (!backendResponse.ok) {
        throw new Error('Failed to send course data to ModuLearn: ' + backendResponse.statusText);
      }

      var result = await backendResponse.json();
      if (!result.success) {
        throw new Error(result.error || 'Unknown error occurred while creating the course.');
      }

      window.location.href = config.redirectUrl;
    } catch (error) {
      console.error('Error during course creation:', error);
      loadingState.classList.add('hidden');
      errorState.classList.remove('hidden');
      errorMessage.textContent = error.message || 'An unexpected error occurred while creating your course.';
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!window.createSemesterCourseConfig) {
      return;
    }
    createCourse(window.createSemesterCourseConfig);
  });
})();
