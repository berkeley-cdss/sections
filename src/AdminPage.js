/* eslint-disable react/no-array-index-key,camelcase */
// @flow strict

import "bootstrap/dist/css/bootstrap.css";
import { useContext, useState } from "react";
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
import { Redirect } from "react-router-dom";
import ImportSectionsModal from "./ImportSectionsModal";
import ImportEnrollmentModal from "./ImportEnrollmentModal";
import StateContext from "./StateContext";
import ToggleSwitch from "./ToggleSwitch";
import useAPI from "./useStateAPI";
import AddStudentModal from "./AddStudentModal";
import ResetSectionsModal from "./ResetSectionsModal";
import MessageContext from "./MessageContext";

export default function AdminPage(): React.Node {
  const { config, currentUser } = useContext(StateContext);

  const { pushMessage } = useContext(MessageContext);

  const [showImportSectionsModal, setShowImportSectionsModal] = useState(false);
  const [showImportEnrollmentModal, setShowImportEnrollmentModal] = useState(false);
  const [message, setMessage] = useState(config.message);

  // const [tabName, setTabName] = useState("");

  const [removing, setRemoving] = useState(false);
  const removeStudents = useAPI("remove_students");
  const [removingTutoring, setRemovingTutoring] = useState(false);
  const removeStudentsFromTutoring = useAPI("remove_students_from_tutoring");

  const updateConfig = useAPI("update_config");
  const exportAttendance = useAPI(
    "export_attendance",
    ({ custom: { attendances, fileName } }) => {
      if (attendances == null || fileName == null) {
        return;
      }
      const element = document.createElement("a");
      element.setAttribute(
        "href",
        `data:text/plain;charset=utf-8,${encodeURIComponent(attendances)}`
      );
      element.setAttribute("download", fileName);

      element.style.display = "none";
      // eslint-disable-next-line no-unused-expressions
      document.body?.appendChild(element);
      element.click();
      // eslint-disable-next-line no-unused-expressions
      document.body?.removeChild(element);
    }
  );
  const exportRosters = useAPI(
    "export_rosters",
    ({ custom: { rosters, fileName } }) => {
      if (rosters == null || fileName == null) {
        return;
      }
      const element = document.createElement("a");
      element.setAttribute(
        "href",
        `data:text/plain;charset=utf-8,${encodeURIComponent(rosters)}`
      );
      element.setAttribute("download", fileName);

      element.style.display = "none";
      // eslint-disable-next-line no-unused-expressions
      document.body?.appendChild(element);
      element.click();
      // eslint-disable-next-line no-unused-expressions
      document.body?.removeChild(element);
    }
  );
  const fetchToDrop = useAPI("fetch_to_drop", ({ custom: {students}}) => {
    if (students == null) {
      return;
    }
    navigator.clipboard.writeText(students);
    pushMessage("Copied");
  });
  const [resetting, setResetting] = useState(false);
  const resetSections = useAPI("reset_sections");

  type ConfigKey = "canStudentsJoinLab" | "canStudentsChangeLab" | "canTutorsChangeLab" | "canTutorsReassignLab" | 
  "canStudentsJoinDiscussion" | "canStudentsChangeDiscussion" | "canTutorsChangeDiscussion" | "canTutorsReassignDiscussion" | 
  "canStudentsJoinTutoring" | "canStudentsChangeTutoring" | "canTutorsChangeTutoring" | 
  "canTutorsReassignTutoring" | string;

  const [tabsConfig, setTabsConfig] = useState<Array<{  // eslint-disable-line no-unused-vars
    eventKey: string,
    title: string,
    settings: Array<{
      label: string,
      configKey: ConfigKey,
      dbKey: string,
    }>,
  }>>([
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
        }
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
        }
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
        }
      ],
    },
  ]);

  // function addTab() {
  //   const newConfigKey: string = `canEnroll${tabName}`; // Flow-compatible annotation for string
  //   const newTab = {
  //     eventKey: tabName.toLowerCase(),
  //     title: tabName,
  //     settings: [
  //       {
  //         label: `Should students be able to enroll in ${tabName}?`,
  //         configKey: newConfigKey, // Dynamically generated key
  //       },
  //     ],
  //   };
  //   setTabsConfig((prevTabs) => [...prevTabs, newTab]);
  // }

  const renderTabContent = (tab) => (
    <>
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
                    updateConfig({ [(setting.dbKey: string)]: value }); // Cast to string
                  }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  );

  if (!currentUser?.isAdmin) {
    return <Redirect to="/" />;
  }

  return (
    <Container>
      <br />
      <Row>
        <Col>
          <Tabs defaultActiveKey="general">
            <Tab eventKey="general" title="General">
              <p>
                Welcome message:
                <InputGroup>
                  <FormControl
                    as="textarea"
                    placeholder="Write a short welcome message for students"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                  />
                  <InputGroup.Append>
                    <Button
                      variant="outline-secondary"
                      onClick={() => updateConfig({ message })}
                    >
                      Save
                    </Button>
                  </InputGroup.Append>
                </InputGroup>
              </p>
              <p>
                Preview of welcome message:
                <Alert variant="info">
                  <ReactMarkdown>{message}</ReactMarkdown>
                </Alert>
              </p>

              {/* Line 1: Import Buttons */}
              <p>
                <Button
                  variant="secondary"
                  onClick={() => setShowImportSectionsModal(true)}
                >
                  Import Sections
                </Button>{" "}
                <Button
                  variant="secondary"
                  onClick={() => setShowImportEnrollmentModal(true)}
                >
                  Import Students
                </Button>
              </p>

              {/* Line 2: Export Buttons */}
              <p>
                <Button
                  variant="secondary"
                  onClick={() => exportRosters({})}
                >
                  Export Rosters
                </Button>{" "}
                <Button
                  variant="secondary"
                  onClick={() => exportAttendance({})}
                >
                  Export Full Attendances
                </Button>
              </p>

              {/* Line 3: Description Text */}
              <p>
                The following will obtain emails of students who have at least one unexcused absence or 3 excused absences in their enrolled tutoring section.
              </p>

              {/* Line 4: Copy Students to Drop */}
              <p>
                <Button
                  variant="secondary"
                  onClick={() => fetchToDrop()}
                >
                  Copy Students To Drop (Tutoring)
                </Button>{" "}
                <Button
                  variant="danger"
                  onClick={() => setRemovingTutoring(true)}
                >
                  Remove Students from Tutoring
                </Button>
                <AddStudentModal
                  show={removingTutoring}
                  title="Remove student(s) from Tutoring sections"
                  onAdd={(students) => removeStudentsFromTutoring({ students })}
                  onClose={() => setRemovingTutoring(false)}
                />
              </p>

              {/* Line 5: Admin Management Actions */}
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
            {tabsConfig.map((tab) => (
              <Tab key={tab.eventKey} eventKey={tab.eventKey} title={tab.title}>
                {renderTabContent(tab)}
              </Tab>
            ))}
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
    </Container>
  );
}