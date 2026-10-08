import * as React from "react";
import styled from "styled-components";

// Bootstrap 5 dropped the jumbotron; this matches Bootstrap 4's fluid one.
const Hero = styled.div`
  padding: 4rem 0;
  margin-bottom: 2rem;
  background-color: #e9ecef;
`;

export default function HeroBanner({ children }: { children: React.ReactNode }) {
  return <Hero>{children}</Hero>;
}
