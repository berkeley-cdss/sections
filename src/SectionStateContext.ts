import * as React from "react";

import type { SectionDetails } from "./models";

export default React.createContext<
  SectionDetails & {
    updateState: (state: SectionDetails) => void;
  }
>({
  id: "",
  staff: null,
  students: [],
  enrollmentCount: 0,
  description: "",
  capacity: 0,
  startTime: 0,
  endTime: 0,
  callLink: null,
  tags: [],
  updateState: () => {},
  canSelfEnroll: false,
  needsEnrollmentCode: false,
  enrollmentCode: null,
  name: "",
  location: "",
  sessions: [],
});
