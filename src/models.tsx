import moment from "moment-timezone";
import * as React from "react";

export type ID = string;
export type Time = number;

export type Person = {
  id: ID;
  name: string;
  email: string;
  isStaff: boolean;
  preferredName?: string | null;
};

export type Section = {
  id: ID;
  staff: Person | null;
  students: Array<Person>;
  enrollmentCount?: number;
  description: string;
  capacity: number;
  tags: Array<string>;
  needsEnrollmentCode: boolean;
  canSelfEnroll: boolean;
  enrollmentCode: string | null;
  // formerly in slot
  name: string;
  startTime: Time;
  endTime: Time;
  callLink: string | null;
  location: string;
};

const AttendanceStatus = {
  present: "Present",
  excused: "Excused",
  absent: "Absent",
};

export { AttendanceStatus };

export type AttendanceStatusType = keyof typeof AttendanceStatus;

type Attendance = {
  student: Person;
  status: AttendanceStatusType;
};

export type Session = {
  id: ID;
  startTime: Time;
  attendances: Array<Attendance>;
};

type AttendanceDetails = Attendance & {
  section: Section | null;
  session: Session;
};

export type PersonDetails = Person & {
  isAdmin?: boolean;
  attendanceHistory: Array<AttendanceDetails>;
};

export type SectionDetails = Section & {
  sessions: Array<Session>;
};

export type CourseConfig = {
  canStudentsJoinLab: boolean;
  canStudentsChangeLab: boolean;
  canTutorsChangeLab: boolean;
  canTutorsReassignLab: boolean;
  canStudentsJoinDiscussion: boolean;
  canStudentsChangeDiscussion: boolean;
  canTutorsChangeDiscussion: boolean;
  canTutorsReassignDiscussion: boolean;
  canStudentsJoinTutoring: boolean;
  canStudentsChangeTutoring: boolean;
  canTutorsChangeTutoring: boolean;
  canTutorsReassignTutoring: boolean;
  message: string;
};

export type State = {
  course: string;
  enrolledSections: Array<Section> | null;
  sections: Array<Section>;
  taughtSections: Array<Section>;
  currentUser: PersonDetails | null;
  config: CourseConfig;
  // Google account to share import spreadsheets with, if configured.
  serviceAccountEmail: string | null;
};

export const TZ = "America/Los_Angeles";

export function sectionTitle(section: Section | null | undefined): React.ReactElement {
  return section == null ? (
    <>Deleted Section</>
  ) : (
    <>
      {section.staff == null ? "Unknown TA" : `${section.staff.name}'s section`}{" "}
    </>
  );
}

export function getEnrollmentCount(section: Section): number {
  return section.enrollmentCount ?? section.students.length;
}

export function nextSessionStartTime(section: Section, dayOffset: number = 0) {
  const time = moment.unix(section.startTime).tz(TZ);
  while (time.isBefore(moment().add(dayOffset, "days"))) {
    time.add(7, "days");
  }
  return time.local();
}

export function sessionStartTimes(section: Section) {
  let time = moment.unix(section.startTime).tz(TZ);
  const out = [];
  while (time.isBefore(moment().subtract(1.5, "days"))) {
    out.push(time.clone().local());
    time = time.clone().add(7, "days");
  }
  return out;
}

export function sectionInterval(section: Section): React.ReactElement {
  const isPT = moment.tz.guess() === TZ;
  const useLocalString = document.cookie
    .split("; ")
    .find((row) => row.startsWith("useLocal="));
  const useLocal = useLocalString && useLocalString.split("=")[1] === "true";

  const tz = useLocal ? moment.tz.guess() : TZ;

  const firstSectionStartTime = moment.unix(section.startTime).tz(tz);
  const startTime = nextSessionStartTime(section);
  const endTime = startTime
    .clone()
    .add(section.endTime - section.startTime, "seconds");
  return (
    <>
      {firstSectionStartTime.tz(tz).format("ddd")}{" "}
      {startTime.tz(tz).format("h:mma")} &rarr; {endTime.tz(tz).format("h:mma")}
      {!isPT && <> ({moment().tz(tz).format("z")})</>}
    </>
  );
}

export function getSectionStartTime(section: Section) {
  const time = moment.unix(section.startTime).tz(TZ);
  return time.format("hh:mma").replace("m", "");
}

export function getSectionEndTime(section: Section) {
  const time = moment.unix(section.endTime).tz(TZ);
  return time.format("hh:mma").replace("m", "");
}

export function getSectionDay(section: Section) {
  const time = moment.unix(section.startTime).tz(TZ);
  const dayCodes = ["M", "T", "W", "Th", "F"];
  const dayIndex = time.day() - 1;
  return dayCodes[dayIndex];
}

export function sortedSections<T extends Section | SectionDetails>(
  sections: Array<T>
): Array<T> {
  return sections
    .slice()
    .sort((section1, section2) =>
      nextSessionStartTime(section1).diff(nextSessionStartTime(section2))
    );
}

// Config flags are named per section type, e.g. canStudentsJoinLab or
// canTutorsChangeDiscussion, where the suffix is a section's name.
export function configAllows(
  config: CourseConfig,
  flag: "canStudentsJoin" | "canStudentsChange" | "canTutorsChange" | "canTutorsReassign",
  sectionName: string
): boolean {
  return (config as { [key: string]: unknown })[`${flag}${sectionName}`] === true;
}
