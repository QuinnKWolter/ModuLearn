/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.html',
    './accounts/templates/**/*.html',
    './courses/templates/**/*.html',
    './dashboard/templates/**/*.html',
    './lti/templates/**/*.html',
    './main/templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
