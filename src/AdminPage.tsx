import "bootstrap/dist/css/bootstrap.css";
import { useCallback, useContext, useRef, useState } from "react";
import * as React from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Tab from "react-bootstrap/Tab";
import Table from "react-bootstrap/Table";
import Tabs from "react-bootstrap/Tabs";
import FormControl from "react-bootstrap/FormControl";
import InputGroup from "react-bootstrap/InputGroup";
import Container from "react-bootstrap/Container";
import Row from "react-bootstrap/Row";
import ReactMarkdown from "react-markdown";
import { Navigate } from "react-router-dom";
import ApiKeysTab from "./ApiKeysTab";
import ImportSectionsModal from "./ImportSectionsModal";
import ImportEnrollmentModal from "./ImportEnrollmentModal";
import type { CourseConfig } from "./models";
import StateContext from "./StateContext";
import ToggleSwitch from "./ToggleSwitch";
import useAPI from "./useStateAPI";
import useBareAPI from "./useAPI";
import AddStudentModal from "./AddStudentModal";
import ResetSectionsModal from "./ResetSectionsModal";
import StudentSearch from "./StudentSearch";
import SyncBcoursesModal from "./SyncBcoursesModal";
import MessageContext from "./MessageContext";

type ConfigKey = Exclude<keyof CourseConfig, "message" | "staffUrl">;

type SettingsTab = {
  eventKey: string;
  title: string;
  settings: Array<{
    label: string;
    configKey: ConfigKey;
    dbKey: string;
  }>;
};

const TABS: Array<SettingsTab> = [
  {
    eventKey: "lab",
    title: "Lab",
    settings: [
      {
        label: "Should students be able to enroll in lab sections?",
        configKey: "canStudentsJoinLab",
        dbKey: "can_students_join_lab",
      },
      {
        label: " Should students be able to leave their lab section and join a new one?",
        configKey: "canStudentsChangeLab",
        dbKey: "can_students_change_lab",
      },
      {
        label: "Should tutors be able to leave their lab section, or claim new unassigned lab sections?",
        configKey: "canTutorsChangeLab",
        dbKey: "can_tutors_change_lab",
      },
      {
        label: "Should tutors be able to remove other tutors from their lab sections?",
        configKey: "canTutorsReassignLab",
        dbKey: "can_tutors_reassign_lab",
      },
    ],
  },
  {
    eventKey: "disc",
    title: "Discussion",
    settings: [
      {
        label: "Should students be able to enroll in discussion sections?",
        configKey: "canStudentsJoinDiscussion",
        dbKey: "can_students_join_disc",
      },
      {
        label: " Should students be able to leave their discussion section and join a new one?",
        configKey: "canStudentsChangeDiscussion",
        dbKey: "can_students_change_disc",
      },
      {
        label: "Should tutors be able to leave their discussion section, or claim new unassigned discussion sections?",
        configKey: "canTutorsChangeDiscussion",
        dbKey: "can_tutors_change_disc",
      },
      {
        label: "Should tutors be able to remove other tutors from their discussion sections?",
        configKey: "canTutorsReassignDiscussion",
        dbKey: "can_tutors_reassign_disc",
      },
    ],
  },
  {
    eventKey: "tutoring",
    title: "Tutoring",
    settings: [
      {
        label: "Should students be able to enroll in tutoring sections?",
        configKey: "canStudentsJoinTutoring",
        dbKey: "can_students_join_tutoring",
      },
      {
        label: " Should students be able to leave their tutoring section and join a new one?",
        configKey: "canStudentsChangeTutoring",
        dbKey: "can_students_change_tutoring",
      },
      {
        label: "Should tutors be able to leave their tutoring section, or claim new unassigned tutoring sections?",
        configKey: "canTutorsChangeTutoring",
        dbKey: "can_tutors_change_tutoring",
      },
      {
        label: "Should tutors be able to remove other tutors from their tutoring sections?",
        configKey: "canTutorsReassignTutoring",
        dbKey: "can_tutors_reassign_tutoring",
      },
    ],
  },
];

function downloadText(contents: string, fileName: string) {
  const element = document.createElement("a");
  element.setAttribute("href", `data:text/plain;charset=utf-8,${encodeURIComponent(contents)}`);
  element.setAttribute("download", fileName);
  element.style.display = "none";
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
}

export default function AdminPage(): React.ReactNode {
  const { config, currentUser } = useContext(StateContext);

  const { pushMessage } = useContext(MessageContext);

  const [showImportSectionsModal, setShowImportSectionsModal] = useState(false);
  const [showImportEnrollmentModal, setShowImportEnrollmentModal] = useState(false);
  const [showSyncBcoursesModal, setShowSyncBcoursesModal] = useState(false);
  const [message, setMessage] = useState(config.message);
  const [staffUrl, setStaffUrl] = useState(config.staffUrl ?? "");
  const [savingStaffUrl, setSavingStaffUrl] = useState(false);
  const [staffUrlStatus, setStaffUrlStatus] = useState<{ text: string; variant: "success" | "danger" } | null>(
    null
  );

  const [removing, setRemoving] = useState(false);
  const removeStudents = useAPI("remove_students");
  const [removingTutoring, setRemovingTutoring] = useState(false);
  const removeStudentsFromTutoring = useAPI("remove_students_from_tutoring");

  const updateConfig = useAPI("update_config");
  const exportAttendance = useAPI("export_attendance", ({ custom: { attendances, fileName } }) => {
    if (attendances == null || fileName == null) {
      return;
    }
    downloadText(attendances, fileName);
  });
  const exportRosters = useAPI("export_rosters", ({ custom: { rosters, fileName } }) => {
    if (rosters == null || fileName == null) {
      return;
    }
    downloadText(rosters, fileName);
  });
  // Doesn't change the state, so no need to refresh it.
  const exportStudents = useBareAPI(
    "export_students",
    useCallback(({ custom: { students, fileName } }: { custom: { students: string; fileName: string } }) => {
      downloadText(students, fileName);
    }, [])
  );
  const fetchToDrop = useAPI("fetch_to_drop", ({ custom: { students } }) => {
    if (students == null) {
      return;
    }
    navigator.clipboard.writeText(students);
    pushMessage("Copied");
  });
  const [resetting, setResetting] = useState(false);
  const resetSections = useAPI("reset_sections");

  // Set by the success callback, so we know whether the save went through; a
  // failure has already shown its error at the top of the page.
  const staffUrlSaved = useRef(false);
  const updateStaffUrl = useAPI(
    "update_config",
    useCallback(() => {
      staffUrlSaved.current = true;
    }, [])
  );
  const saveStaffUrl = async () => {
    setStaffUrlStatus(null);
    setSavingStaffUrl(true);
    staffUrlSaved.current = false;
    await updateStaffUrl({ staff_url: staffUrl });
    setSavingStaffUrl(false);
    if (staffUrlSaved.current) {
      const url = staffUrl.trim();
      setStaffUrl(url);
      setStaffUrlStatus({
        text: url ? "Staff page URL saved." : "Staff page link removed.",
        variant: "success",
      });
    } else {
      setStaffUrlStatus({
        text: "The staff page URL wasn't saved. See the error at the top of the page.",
        variant: "danger",
      });
    }
  };

  const renderTabContent = (tab: SettingsTab) => (
    <Table striped hover>
      <thead>
        <tr>
          <th>Options</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {tab.settings.map((setting, index) => (
          <tr key={index}>
            <td>{setting.label}</td>
            <td>
              <ToggleSwitch
                defaultChecked={config[setting.configKey]}
                onChange={(value) => {
                  updateConfig({ [setting.dbKey]: value });
                }}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );

  if (!currentUser?.isAdmin) {
    return <Navigate to="/" replace />;
  }

  return (
    <Container>
      <br />
      <h1 className="h2">Admin Settings</h1>
      <Row>
        <Col>
          <Tabs defaultActiveKey="general" className="mb-3">
            <Tab eventKey="general" title="General">
              <div className="mb-3">
                Welcome message:
                <InputGroup>
                  <FormControl
                    as="textarea"
                    placeholder="Write a short welcome message for students"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                  />
                  <Button variant="outline-secondary" onClick={() => updateConfig({ message })}>
                    Save
                  </Button>
                </InputGroup>
              </div>
              <div className="mb-3">
                Preview of welcome message:
                <Alert variant="info">
                  <ReactMarkdown>{message}</ReactMarkdown>
                </Alert>
              </div>
              <div className="mb-3">
                <label htmlFor="staff-url">Staff page URL:</label>
                <InputGroup>
                  <FormControl
                    id="staff-url"
                    type="url"
                    placeholder="https://example.berkeley.edu/staff/"
                    aria-describedby="staff-url-help"
                    value={staffUrl}
                    onChange={(e) => setStaffUrl(e.target.value)}
                  />
                  <Button variant="outline-secondary" onClick={saveStaffUrl} disabled={savingStaffUrl}>
                    {savingStaffUrl ? "Saving…" : "Save"}
                  </Button>
                </InputGroup>
                <div id="staff-url-help" className="form-text">
                  Shown as &ldquo;Staff&rdquo; in the nav bar. Use this semester&rsquo;s staff page; leave it blank
                  for no link.
                </div>
                {staffUrlStatus != null ? (
                  <Alert
                    className="mt-2"
                    variant={staffUrlStatus.variant}
                    onClose={() => setStaffUrlStatus(null)}
                    dismissible
                  >
                    {staffUrlStatus.text}
                  </Alert>
                ) : null}
              </div>
            </Tab>
            <Tab eventKey="roster" title="Roster Management">
              <p className="mb-1">At the start of the semester, start by:</p>
              <ol>
                <li>syncing the bCourses student roster,</li>
                <li>importing sections,</li>
                <li>importing section assignments.</li>
              </ol>
              <p>
                It is safe to run any of these steps again. For example, if you want to drop students from sections
                who have dropped your course, re-run the bCourses sync. You can also add more sections after your
                initial setup, and assign students in multiple rounds (like if they added the course late).
              </p>
              <p>
                <Button variant="secondary" onClick={() => setShowSyncBcoursesModal(true)}>
                  Sync bCourses Students
                </Button>{" "}
                <Button variant="secondary" onClick={() => setShowImportSectionsModal(true)}>
                  Import Sections
                </Button>{" "}
                <Button variant="secondary" onClick={() => setShowImportEnrollmentModal(true)}>
                  Import Section Assignments
                </Button>
              </p>

              <StudentSearch />

              <p>
                <Button variant="secondary" onClick={() => exportRosters({})}>
                  Export Section Assignments
                </Button>{" "}
                <Button variant="secondary" onClick={() => exportAttendance({})}>
                  Export Full Attendances
                </Button>{" "}
                <Button variant="secondary" onClick={() => exportStudents({})}>
                  Export Students
                </Button>
              </p>
              <ul className="text-muted small">
                <li>
                  &ldquo;Export Section Assignments&rdquo; (CSV) has one row per student per section, in the format
                  &ldquo;Import Section Assignments&rdquo; reads, so you can export, edit the spreadsheet, and import
                  it back. Students in no section aren&rsquo;t in it.
                </li>
                <li>
                  &ldquo;Export Full Attendances&rdquo; (JSON) has every attendance record, by section type and
                  student. All students who have had attendance recorded are included in this export, even if the
                  student has been removed from a section or this course offering.
                </li>
                <li>
                  &ldquo;Export Students&rdquo; (CSV) has one row per student in the offering, with their section of
                  each type, or &ldquo;Floating&rdquo; if they have no lab or discussion section. Run &ldquo;Sync
                  bCourses Students&rdquo; first so it includes students who&rsquo;ve just joined and leaves out
                  those who&rsquo;ve dropped.
                </li>
              </ul>

              <p>
                <Button variant="secondary" onClick={() => fetchToDrop()}>
                  Copy Students To Drop (Tutoring)
                </Button>{" "}
                <Button variant="danger" onClick={() => setRemovingTutoring(true)}>
                  Remove Students from Tutoring
                </Button>
                <AddStudentModal
                  show={removingTutoring}
                  title="Remove student(s) from Tutoring sections"
                  onAdd={(students) => removeStudentsFromTutoring({ students })}
                  onClose={() => setRemovingTutoring(false)}
                />
              </p>
              <p className="text-muted small">
                &ldquo;Copy Students To Drop (Tutoring)&rdquo; copies the emails of students who have at least one
                unexcused absence or 3 excused absences in their tutoring section.
              </p>

              {currentUser?.isAdmin && (
                <p>
                  <Button variant="danger" onClick={() => setRemoving(true)}>
                    Remove Students from All Sections
                  </Button>
                  <AddStudentModal
                    show={removing}
                    title="Remove student(s) from All Sections"
                    onAdd={(students) => removeStudents({ students })}
                    onClose={() => setRemoving(false)}
                  />{" "}
                  <Button variant="danger" onClick={() => setResetting(true)}>
                    Reset Sections Tool
                  </Button>
                  <ResetSectionsModal
                    show={resetting}
                    onReset={() => resetSections()}
                    onClose={() => setResetting(false)}
                  />
                </p>
              )}
            </Tab>
            {TABS.map((tab) => (
              <Tab key={tab.eventKey} eventKey={tab.eventKey} title={tab.title}>
                {renderTabContent(tab)}
              </Tab>
            ))}
            <Tab eventKey="api-keys" title="API Keys" mountOnEnter>
              <ApiKeysTab />
            </Tab>
          </Tabs>
        </Col>
      </Row>
      <ImportSectionsModal
        show={showImportSectionsModal}
        onClose={() => setShowImportSectionsModal(false)}
      />
      <ImportEnrollmentModal
        show={showImportEnrollmentModal}
        onClose={() => setShowImportEnrollmentModal(false)}
      />
      <SyncBcoursesModal show={showSyncBcoursesModal} onClose={() => setShowSyncBcoursesModal(false)} />
    </Container>
  );
}
