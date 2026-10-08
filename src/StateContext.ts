import * as React from "react";

import type { State } from "./models";

export default React.createContext<
  State & {
    updateState: (state: State) => void;
  }
>({
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
  taughtSections: [],
  enrolledSections: [],
  updateState: () => {},
});
