// @flow strict

// Each course's pages live under /offerings/<canvas course id>/ (as in seating); this is that
// prefix for the current page, used as the router basename and for API calls.
const match = window.location.pathname.match(/^\/offerings\/\d+/);

const COURSE_BASE: string = match ? match[0] : "";

export default COURSE_BASE;
