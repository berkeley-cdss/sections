// @flow strict

import * as React from "react";

import type { State } from "./models";

export default React.createContext<{
  ...State,
  updateState: (State) => void,
}>({
  course: "",
  config: {
    canStudentsJoinLab: true, 
    canStudentsChangeLab: true,
    canTutorsChangeLab: true,
    canTutorsReassignLab: true,
    canStudentsJoinDiscussion: true,
    canStudentsChangeDiscussion: true,
    canTutorsChangeDiscussion: true,
    canTutorsReassignDiscussion: true,
    canStudentsJoinTutoring: true,
    canStudentsChangeTutoring: true,
    canTutorsChangeTutoring: true,
    canTutorsReassignTutoring: true,
    message: "",
  },
  currentUser: null,
  serviceAccountEmail: null,
  sections: [],
  history: [],
  taughtSections: [],
  enrolledSections: [],
  updateState: () => {},
});
